#include "EventAction.hh"

#include "SimIO.hh"
#include "config.hh"

#include "G4AutoLock.hh"
#include "G4Event.hh"
#include "G4ParticleDefinition.hh"
#include "G4PrimaryParticle.hh"
#include "G4PrimaryVertex.hh"
#include "G4SystemOfUnits.hh"
#include "G4UnitsTable.hh"
#include "G4ios.hh"

#include <cstdint>
#include <string>
#include <unordered_set>
#include <vector>

/**
 * EventAction is the per-event aggregation layer for this simulation.
 *
 * Responsibilities:
 * - Capture primary metadata from the Geant4 event.
 * - Collect cross-step/cross-track context (track origins and photon ancestry).
 * - Accumulate per-photon optical-interface-hit records.
 * - Transform collected data into IO row containers at end-of-event.
 * - Delegate all file writing to SimIO (CSV/HDF5) under one write lock.
 */
namespace {
/**
 * Global mutex used to serialize file output at end-of-event.
 *
 * Why global:
 * - EventAction instances are thread-local in Geant4 MT mode.
 * - Output files (CSV/HDF5) are shared resources.
 * - We need one cross-thread lock to avoid interleaved writes.
 */
G4Mutex gOutputMutex = G4MUTEX_INITIALIZER;

/**
 * Convert Geant4 particle names into compact labels used in output tables.
 */
std::string ToSpeciesLabel(const G4String& particleName) {
  if (particleName == "neutron") return "n";
  if (particleName == "gamma") return "g";
  if (particleName == "alpha") return "a";
  if (particleName == "proton") return "p";
  if (particleName == "e-") return "electron";
  if (particleName == "e+") return "positron";

  const auto bracket = particleName.find('[');
  if (bracket != std::string::npos) {
    return particleName.substr(0, bracket);
  }
  return particleName;
}

/**
 * Return true when output mode requires CSV emission.
 */
bool WritesCsv(Config::OutputFormat mode) {
  return mode == Config::OutputFormat::kCsv ||
         mode == Config::OutputFormat::kBoth;
}

/**
 * Return true when output mode requires HDF5 emission.
 */
bool WritesHdf5(Config::OutputFormat mode) {
  return mode == Config::OutputFormat::kHdf5 ||
         mode == Config::OutputFormat::kBoth;
}
}  // namespace

G4ThreadLocal EventAction* EventAction::fgInstance = nullptr;

/**
 * Construct thread-local EventAction.
 *
 * Geant4 creates one EventAction instance per worker thread in MT mode.
 * We store a thread-local back-pointer so other user actions (tracking/SD)
 * can access event-local state via EventAction::Instance().
 */
EventAction::EventAction(const Config* config) : fConfig(config) {
  fgInstance = this;
}

/**
 * Clear thread-local singleton pointer on destruction.
 */
EventAction::~EventAction() { fgInstance = nullptr; }

/**
 * Return the EventAction instance for the current thread.
 */
EventAction* EventAction::Instance() { return fgInstance; }

/**
 * Begin-of-event callback.
 *
 * Reset all per-event caches and extract primary-particle metadata from the
 * first primary vertex when available.
 */
void EventAction::BeginOfEventAction(const G4Event* event) {
  // Reset event-local aggregates and caches.
  fEdep = 0.0;
  fPrimarySpecies = "unknown";
  fPrimaryPosition = G4ThreeVector();
  fPrimaryEnergy = -1.0;
  fTrackInfo.clear();
  fPhotonCreationInfo.clear();
  fPendingPhotonOrigin.clear();
  fPhotonHits.clear();

  if (!event) {
    return;
  }

  const auto* primaryVertex = event->GetPrimaryVertex();
  if (!primaryVertex) {
    return;
  }

  fPrimaryPosition = primaryVertex->GetPosition();
  const auto* primaryParticle = primaryVertex->GetPrimary();
  if (!primaryParticle) {
    return;
  }

  if (const auto* def = primaryParticle->GetParticleDefinition()) {
    fPrimarySpecies = ToSpeciesLabel(def->GetParticleName());
  }
  fPrimaryEnergy = primaryParticle->GetKineticEnergy();
}

/**
 * End-of-event callback.
 *
 * Workflow:
 * 1. Emit lightweight progress every 1000 simulated events.
 * 2. Build row containers for enabled output mode(s).
 *    - CSV rows keep the legacy flat optical-interface-hit schema.
 *    - HDF5 photon rows include optical-interface crossing ray metadata
 *      (direction, polarization, energy, wavelength).
 * 3. Serialize rows through SimIO under a shared file-write mutex.
 */
void EventAction::EndOfEventAction(const G4Event* event) {
  const auto eventID = event ? event->GetEventID() : -1;
  const auto simulatedCount = eventID + 1;
  if (simulatedCount > 0 && (simulatedCount % 1000 == 0)) {
    G4cout << "Simulated " << simulatedCount << " events" << G4endl;
  }

  auto outputMode = Config::OutputFormat::kCsv;
  if (fConfig) {
    outputMode = fConfig->GetOutputFormat();
  }

  if (!event) {
    return;
  }

  const auto eventID64 = static_cast<std::int64_t>(event->GetEventID());
  const std::string csvPath =
      fConfig ? fConfig->GetCsvFilePath() : "photon_optical_interface_hits.csv";
  const std::string hdf5Path =
      fConfig ? fConfig->GetHdf5FilePath() : "photon_optical_interface_hits.h5";

  // Build flat CSV rows (one row per detected photon hit).
  std::vector<SimIO::CsvPhotonHitInfo> csvRows;
  if (WritesCsv(outputMode)) {
    csvRows.reserve(fPhotonHits.size());
    for (const auto& hit : fPhotonHits) {
      SimIO::CsvPhotonHitInfo row;
      row.eventId = eventID64;
      row.primaryId = static_cast<std::int32_t>(hit.primaryID);
      row.secondaryId = static_cast<std::int32_t>(hit.secondaryID);
      row.photonId = static_cast<std::int32_t>(hit.photonID);
      row.primarySpecies = hit.primarySpecies;
      row.primaryXmm = hit.primaryX / mm;
      row.primaryYmm = hit.primaryY / mm;
      row.secondarySpecies = hit.secondarySpecies;
      row.secondaryOriginXmm = hit.secondaryOriginPosition.x() / mm;
      row.secondaryOriginYmm = hit.secondaryOriginPosition.y() / mm;
      row.secondaryOriginZmm = hit.secondaryOriginPosition.z() / mm;
      row.secondaryOriginEnergyMeV = hit.secondaryOriginEnergy / MeV;
      row.scintOriginXmm = hit.scintOriginPosition.x() / mm;
      row.scintOriginYmm = hit.scintOriginPosition.y() / mm;
      row.scintOriginZmm = hit.scintOriginPosition.z() / mm;
      row.opticalInterfaceHitXmm = hit.opticalInterfaceHitPosition.x() / mm;
      row.opticalInterfaceHitYmm = hit.opticalInterfaceHitPosition.y() / mm;
      csvRows.push_back(row);
    }
  }

  std::vector<SimIO::PrimaryInfo> primaryRows;
  std::vector<SimIO::SecondaryInfo> secondaryRows;
  std::vector<SimIO::PhotonInfo> photonRows;
  if (WritesHdf5(outputMode)) {
    // Primaries: deduplicate by primary track ID.
    std::unordered_set<G4int> seenPrimary;
    for (const auto& hit : fPhotonHits) {
      if (hit.primaryID < 0 || !seenPrimary.insert(hit.primaryID).second) {
        continue;
      }

      SimIO::PrimaryInfo row;
      row.gunCallId = eventID64;
      row.primaryTrackId = static_cast<std::int32_t>(hit.primaryID);
      row.primarySpecies = hit.primarySpecies;
      row.primaryXmm = hit.primaryX / mm;
      row.primaryYmm = hit.primaryY / mm;
      row.primaryEnergyMeV = fPrimaryEnergy / MeV;
      if (const auto* info = FindTrackInfo(hit.primaryID)) {
        row.primaryEnergyMeV = info->originEnergy / MeV;
      }
      primaryRows.push_back(row);
    }

    // Ensure each event has at least one primary row even when no photon carries
    // a resolved primary ID (e.g., empty-hit events or unresolved ancestry).
    if (primaryRows.empty()) {
      SimIO::PrimaryInfo row;
      row.gunCallId = eventID64;
      row.primaryTrackId = 1;
      row.primarySpecies = fPrimarySpecies;
      row.primaryXmm = fPrimaryPosition.x() / mm;
      row.primaryYmm = fPrimaryPosition.y() / mm;
      row.primaryEnergyMeV = fPrimaryEnergy / MeV;
      primaryRows.push_back(row);
    }

    // Secondaries: deduplicate by secondary track ID.
    std::unordered_set<G4int> seenSecondary;
    for (const auto& hit : fPhotonHits) {
      if (hit.secondaryID < 0 || !seenSecondary.insert(hit.secondaryID).second) {
        continue;
      }

      SimIO::SecondaryInfo row;
      row.gunCallId = eventID64;
      row.primaryTrackId = static_cast<std::int32_t>(hit.primaryID);
      row.secondaryTrackId = static_cast<std::int32_t>(hit.secondaryID);
      row.secondarySpecies = hit.secondarySpecies;
      row.secondaryOriginXmm = hit.secondaryOriginPosition.x() / mm;
      row.secondaryOriginYmm = hit.secondaryOriginPosition.y() / mm;
      row.secondaryOriginZmm = hit.secondaryOriginPosition.z() / mm;
      row.secondaryOriginEnergyMeV = hit.secondaryOriginEnergy / MeV;
      secondaryRows.push_back(row);
    }

    // Photons: one output row per detected optical photon hit.
    // Capture both scintillation-origin location and optical-interface crossing ray state.
    // Unit conversions:
    // - positions -> mm
    // - energy -> eV
    // - wavelength -> nm
    photonRows.reserve(fPhotonHits.size());
    for (const auto& hit : fPhotonHits) {
      SimIO::PhotonInfo row;
      row.gunCallId = eventID64;
      row.primaryTrackId = static_cast<std::int32_t>(hit.primaryID);
      row.secondaryTrackId = static_cast<std::int32_t>(hit.secondaryID);
      row.photonTrackId = static_cast<std::int32_t>(hit.photonID);
      row.photonOriginXmm = hit.scintOriginPosition.x() / mm;
      row.photonOriginYmm = hit.scintOriginPosition.y() / mm;
      row.photonOriginZmm = hit.scintOriginPosition.z() / mm;
      row.opticalInterfaceHitXmm = hit.opticalInterfaceHitPosition.x() / mm;
      row.opticalInterfaceHitYmm = hit.opticalInterfaceHitPosition.y() / mm;
      row.opticalInterfaceHitDirX = hit.opticalInterfaceHitDirection.x();
      row.opticalInterfaceHitDirY = hit.opticalInterfaceHitDirection.y();
      row.opticalInterfaceHitDirZ = hit.opticalInterfaceHitDirection.z();
      row.opticalInterfaceHitPolX = hit.opticalInterfaceHitPolarization.x();
      row.opticalInterfaceHitPolY = hit.opticalInterfaceHitPolarization.y();
      row.opticalInterfaceHitPolZ = hit.opticalInterfaceHitPolarization.z();
      row.opticalInterfaceHitEnergyEV = hit.opticalInterfaceHitEnergy / eV;
      row.opticalInterfaceHitWavelengthNm = hit.opticalInterfaceHitWavelength / nm;
      photonRows.push_back(row);
    }
  }

  // Serialize with one process-global lock because files are shared across
  // worker threads.
  G4AutoLock lock(&gOutputMutex);
  if (WritesCsv(outputMode)) {
    std::string error;
    if (!SimIO::AppendCsv(csvPath, csvRows, &error)) {
      G4cout << (error.empty() ? "Failed writing CSV output." : error) << G4endl;
    }
  }

  if (WritesHdf5(outputMode)) {
    std::string error;
    if (!SimIO::AppendHdf5(hdf5Path, primaryRows, secondaryRows, photonRows,
                           &error)) {
      if (error.empty()) {
        G4cout << "Failed writing HDF5 output to " << hdf5Path << G4endl;
      } else {
        G4cout << error << G4endl;
      }
    }
  }
}

/**
 * Record per-track origin information.
 *
 * Called by TrackingAction when Geant4 starts tracking a new particle.
 */
void EventAction::RecordTrackInfo(G4int trackID, const TrackInfo& info) {
  fTrackInfo[trackID] = info;
}

/**
 * Look up previously recorded track information by Geant4 track ID.
 *
 * Returns nullptr when no entry exists for this event.
 */
const EventAction::TrackInfo* EventAction::FindTrackInfo(G4int trackID) const {
  const auto it = fTrackInfo.find(trackID);
  return (it == fTrackInfo.end()) ? nullptr : &it->second;
}

/**
 * Record resolved photon-creation ancestry for one optical photon track.
 */
void EventAction::RecordPhotonCreationInfo(G4int photonTrackID,
                                           const PhotonCreationInfo& info) {
  fPhotonCreationInfo[photonTrackID] = info;
}

/**
 * Retrieve previously recorded photon-creation ancestry.
 *
 * Returns nullptr when ancestry information is unavailable for the photon track.
 */
const EventAction::PhotonCreationInfo* EventAction::FindPhotonCreationInfo(
    G4int photonTrackID) const {
  const auto it = fPhotonCreationInfo.find(photonTrackID);
  return (it == fPhotonCreationInfo.end()) ? nullptr : &it->second;
}

/**
 * Store a pending optical-photon creation position keyed by track pointer.
 *
 * This bridge is used between stepping and tracking callbacks because Geant4
 * creates secondary tracks during stepping before tracking callbacks fire.
 */
void EventAction::RecordPendingPhotonOrigin(const G4Track* photonTrack,
                                            const G4ThreeVector& origin) {
  fPendingPhotonOrigin[photonTrack] = origin;
}

/**
 * Consume and erase a pending photon-origin entry.
 *
 * Returns true if an entry was found. When `origin` is non-null, the stored
 * value is copied out before erasing.
 */
bool EventAction::ConsumePendingPhotonOrigin(const G4Track* photonTrack,
                                             G4ThreeVector* origin) {
  const auto it = fPendingPhotonOrigin.find(photonTrack);
  if (it == fPendingPhotonOrigin.end()) {
    return false;
  }
  if (origin) {
    *origin = it->second;
  }
  fPendingPhotonOrigin.erase(it);
  return true;
}

/**
 * Append one finalized photon optical-interface-hit record for the current event.
 *
 * The record is expected to already contain:
 * - ancestry linkage (primary/secondary IDs and species),
 * - scintillation origin,
 * - optical-interface crossing optical state (position, direction, polarization,
 *   energy, wavelength).
 */
void EventAction::RecordPhotonHit(const PhotonHitRecord& hit) {
  fPhotonHits.push_back(hit);
}
