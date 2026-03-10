#include "EventAction.hh"

#include "SimIO.hh"
#include "config.hh"

#include "G4AutoLock.hh"
#include "G4Event.hh"
#include "G4ParticleDefinition.hh"
#include "G4PrimaryParticle.hh"
#include "G4PrimaryVertex.hh"
#include "G4SystemOfUnits.hh"
#include "G4ios.hh"

#include <algorithm>
#include <cstdint>
#include <limits>
#include <string>
#include <unordered_set>
#include <vector>

namespace {
/// Serialize appends to shared HDF5 output files across worker threads.
G4Mutex gOutputMutex = G4MUTEX_INITIALIZER;

/// Convert Geant4 particle names into compact labels used in output tables.
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

}  // namespace

G4ThreadLocal EventAction* EventAction::fgInstance = nullptr;

EventAction::EventAction(const Config* config) : fConfig(config) {
  fgInstance = this;
}

EventAction::~EventAction() { fgInstance = nullptr; }

EventAction* EventAction::Instance() { return fgInstance; }

void EventAction::BeginOfEventAction(const G4Event* event) {
  fPrimarySpecies = "unknown";
  fPrimaryPosition = G4ThreeVector();
  fPrimaryEnergy = -1.0;
  fTrackInfo.clear();
  fPhotonCreationInfo.clear();
  fPendingPhotonOrigin.clear();
  fPhotonScintillatorExit.clear();
  fSecondaryScintillatorEndpoint.clear();
  fPrimaryScintillatorFirstInteractionTime.clear();
  fPrimaryActivity.clear();
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

void EventAction::EndOfEventAction(const G4Event* event) {
  const auto eventID = event ? event->GetEventID() : -1;
  const auto simulatedCount = eventID + 1;
  if (simulatedCount > 0 && (simulatedCount % 1000 == 0)) {
    G4cout << "Simulated " << simulatedCount << " events" << G4endl;
  }

  if (!event) {
    return;
  }

  const auto eventID64 = static_cast<std::int64_t>(event->GetEventID());
  const std::string hdf5Path =
      fConfig ? fConfig->GetHdf5FilePath() : "photon_optical_interface_hits.h5";

  std::vector<SimIO::PrimaryInfo> primaryRows;
  std::vector<SimIO::SecondaryInfo> secondaryRows;
  std::vector<SimIO::PhotonInfo> photonRows;
  const auto resolvePrimaryInteractionTimeNs = [this](G4int primaryTrackID) -> double {
    const auto it = fPrimaryScintillatorFirstInteractionTime.find(primaryTrackID);
    if (it != fPrimaryScintillatorFirstInteractionTime.end()) {
      return it->second / ns;
    }
    return std::numeric_limits<double>::quiet_NaN();
  };

  // Include only primaries that created at least one secondary in scintillator.
  std::vector<G4int> primaryTrackIDs;
  primaryTrackIDs.reserve(fPrimaryActivity.size());
  for (const auto& entry : fPrimaryActivity) {
    if (entry.second.createdSecondaryCount <= 0) {
      continue;
    }
    primaryTrackIDs.push_back(entry.first);
  }
  std::sort(primaryTrackIDs.begin(), primaryTrackIDs.end());

  for (const auto primaryTrackID : primaryTrackIDs) {
    const auto activityIt = fPrimaryActivity.find(primaryTrackID);
    if (activityIt == fPrimaryActivity.end()) {
      continue;
    }
    const auto& activity = activityIt->second;
    SimIO::PrimaryInfo row;
    row.gunCallId = eventID64;
    row.primaryTrackId = static_cast<std::int32_t>(primaryTrackID);
    row.primarySpecies = fPrimarySpecies;
    row.primaryXmm = fPrimaryPosition.x() / mm;
    row.primaryYmm = fPrimaryPosition.y() / mm;
    row.primaryEnergyMeV = fPrimaryEnergy / MeV;
    row.primaryInteractionTimeNs = resolvePrimaryInteractionTimeNs(primaryTrackID);
    row.primaryCreatedSecondaryCount = activity.createdSecondaryCount;
    row.primaryGeneratedOpticalPhotonCount = activity.generatedOpticalPhotonCount;
    row.primaryDetectedOpticalInterfacePhotonCount =
        activity.detectedOpticalInterfacePhotonCount;
    if (const auto* info = FindTrackInfo(primaryTrackID)) {
      row.primarySpecies = info->species;
      row.primaryXmm = info->originPosition.x() / mm;
      row.primaryYmm = info->originPosition.y() / mm;
      row.primaryEnergyMeV = info->originEnergy / MeV;
    }
    primaryRows.push_back(row);
  }

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
    G4ThreeVector endpoint = hit.secondaryOriginPosition;
    FindSecondaryScintillatorEndpoint(hit.secondaryID, &endpoint);
    row.secondaryEndXmm = endpoint.x() / mm;
    row.secondaryEndYmm = endpoint.y() / mm;
    row.secondaryEndZmm = endpoint.z() / mm;
    secondaryRows.push_back(row);
  }

  // One output row per detected optical-interface photon hit.
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
    row.opticalInterfaceHitTimeNs = hit.opticalInterfaceHitTime / ns;
    row.opticalInterfaceHitDirX = hit.opticalInterfaceHitDirection.x();
    row.opticalInterfaceHitDirY = hit.opticalInterfaceHitDirection.y();
    row.opticalInterfaceHitDirZ = hit.opticalInterfaceHitDirection.z();
    row.photonScintExitXmm =
        hit.hasPhotonScintExitPosition ? hit.photonScintExitPosition.x() / mm
                                       : std::numeric_limits<double>::quiet_NaN();
    row.photonScintExitYmm =
        hit.hasPhotonScintExitPosition ? hit.photonScintExitPosition.y() / mm
                                       : std::numeric_limits<double>::quiet_NaN();
    row.photonScintExitZmm =
        hit.hasPhotonScintExitPosition ? hit.photonScintExitPosition.z() / mm
                                       : std::numeric_limits<double>::quiet_NaN();
    row.opticalInterfaceHitPolX = hit.opticalInterfaceHitPolarization.x();
    row.opticalInterfaceHitPolY = hit.opticalInterfaceHitPolarization.y();
    row.opticalInterfaceHitPolZ = hit.opticalInterfaceHitPolarization.z();
    row.photonCreationTimeNs = hit.photonCreationTime / ns;
    row.opticalInterfaceHitEnergyEV = hit.opticalInterfaceHitEnergy / eV;
    row.opticalInterfaceHitWavelengthNm = hit.opticalInterfaceHitWavelength / nm;
    photonRows.push_back(row);
  }

  G4AutoLock lock(&gOutputMutex);
  std::string error;
  if (!SimIO::AppendHdf5(hdf5Path, primaryRows, secondaryRows, photonRows, &error)) {
    if (error.empty()) {
      G4cout << "Failed writing HDF5 output to " << hdf5Path << G4endl;
    } else {
      G4cout << error << G4endl;
    }
  }
}

void EventAction::RecordTrackInfo(G4int trackID, const TrackInfo& info) {
  fTrackInfo[trackID] = info;
}

const EventAction::TrackInfo* EventAction::FindTrackInfo(G4int trackID) const {
  const auto it = fTrackInfo.find(trackID);
  return (it == fTrackInfo.end()) ? nullptr : &it->second;
}

void EventAction::RecordPhotonCreationInfo(G4int photonTrackID,
                                           const PhotonCreationInfo& info) {
  fPhotonCreationInfo[photonTrackID] = info;
}

const EventAction::PhotonCreationInfo* EventAction::FindPhotonCreationInfo(
    G4int photonTrackID) const {
  const auto it = fPhotonCreationInfo.find(photonTrackID);
  return (it == fPhotonCreationInfo.end()) ? nullptr : &it->second;
}

void EventAction::RecordPendingPhotonOrigin(const G4Track* photonTrack,
                                            const G4ThreeVector& origin) {
  fPendingPhotonOrigin[photonTrack] = origin;
}

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

void EventAction::RecordPhotonScintillatorExit(
    G4int photonTrackID, const G4ThreeVector& position) {
  fPhotonScintillatorExit[photonTrackID] = position;
}

bool EventAction::ConsumePhotonScintillatorExit(G4int photonTrackID,
                                                G4ThreeVector* position) {
  const auto it = fPhotonScintillatorExit.find(photonTrackID);
  if (it == fPhotonScintillatorExit.end()) {
    return false;
  }
  if (position) {
    *position = it->second;
  }
  fPhotonScintillatorExit.erase(it);
  return true;
}

void EventAction::RecordSecondaryScintillatorEndpoint(
    G4int secondaryTrackID, const G4ThreeVector& position) {
  fSecondaryScintillatorEndpoint[secondaryTrackID] = position;
}

bool EventAction::FindSecondaryScintillatorEndpoint(
    G4int secondaryTrackID, G4ThreeVector* position) const {
  const auto it = fSecondaryScintillatorEndpoint.find(secondaryTrackID);
  if (it == fSecondaryScintillatorEndpoint.end()) {
    return false;
  }
  if (position) {
    *position = it->second;
  }
  return true;
}

void EventAction::RecordPrimaryScintillatorFirstInteraction(
    G4int primaryTrackID, G4double globalTime) {
  const auto it = fPrimaryScintillatorFirstInteractionTime.find(primaryTrackID);
  if (it == fPrimaryScintillatorFirstInteractionTime.end() ||
      globalTime < it->second) {
    fPrimaryScintillatorFirstInteractionTime[primaryTrackID] = globalTime;
  }
}

void EventAction::RecordPrimarySecondaryCreation(
    G4int primaryTrackID, G4bool generatedOpticalPhoton) {
  if (primaryTrackID < 0) {
    return;
  }
  auto& activity = fPrimaryActivity[primaryTrackID];
  ++activity.createdSecondaryCount;
  if (generatedOpticalPhoton) {
    ++activity.generatedOpticalPhotonCount;
  }
}

void EventAction::RecordPhotonHit(const PhotonHitRecord& hit) {
  if (hit.primaryID >= 0) {
    ++fPrimaryActivity[hit.primaryID].detectedOpticalInterfacePhotonCount;
  }
  fPhotonHits.push_back(hit);
}
