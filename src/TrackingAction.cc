#include "TrackingAction.hh"

#include "EventAction.hh"

#include "G4ParticleDefinition.hh"
#include "G4Track.hh"

#include <string>

/**
 * TrackingAction captures per-track origin/ancestry metadata as soon as Geant4
 * starts tracking each particle.
 *
 * This is the main place where we attach:
 * - species label,
 * - vertex position/energy,
 * - resolved primary ancestor track ID,
 * and, for optical photons, parent-secondary context used by output rows.
 */
namespace {
/**
 * Convert Geant4 particle names into compact analysis labels.
 *
 * Stable short labels keep CSV/HDF5 records easier to read and post-process.
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
}  // namespace

/**
 * Construct tracking action with access to event-local aggregation state.
 */
TrackingAction::TrackingAction(EventAction* eventAction)
    : fEventAction(eventAction) {}

/**
 * Called by Geant4 before each track is processed.
 *
 * Responsibilities:
 * 1. Record generic track-origin metadata.
 * 2. Resolve and cache primary ancestry (`primaryTrackID`) through parent links.
 * 3. For optical photons, build PhotonCreationInfo so sensor hits can later
 *    include secondary parent and scintillation origin metadata.
 */
void TrackingAction::PreUserTrackingAction(const G4Track* track) {
  if (!fEventAction || !track) {
    return;
  }

  EventAction::TrackInfo trackInfo;
  const auto trackID = track->GetTrackID();
  const auto parentID = track->GetParentID();
  const auto particleName = track->GetParticleDefinition()->GetParticleName();
  trackInfo.species = ToSpeciesLabel(particleName);
  trackInfo.originPosition = track->GetVertexPosition();
  trackInfo.originEnergy = track->GetVertexKineticEnergy();

  // Resolve event-local primary ancestor for this track.
  // - parentID == 0 means Geant4 primary particle.
  // - otherwise inherit ancestor from already-recorded parent track info.
  if (parentID == 0) {
    trackInfo.primaryTrackID = trackID;
  } else if (const auto* parentInfo = fEventAction->FindTrackInfo(parentID)) {
    trackInfo.primaryTrackID = parentInfo->primaryTrackID;
  } else {
    trackInfo.primaryTrackID = -1;
  }
  fEventAction->RecordTrackInfo(trackID, trackInfo);

  // For optical photons, cache creation ancestry used when the sensor SD records
  // the eventual hit. This bridges tracking-time ancestry with SD hit capture.
  if (particleName == "opticalphoton") {
    EventAction::PhotonCreationInfo info;
    info.primaryTrackID = trackInfo.primaryTrackID;
    info.secondaryTrackID = parentID;
    info.scintOriginPosition = track->GetVertexPosition();

    // If stepping recorded a more precise creation point for this newly created
    // secondary track, prefer that value.
    fEventAction->ConsumePendingPhotonOrigin(track, &info.scintOriginPosition);

    if (parentID > 0) {
      if (const auto* parentInfo = fEventAction->FindTrackInfo(parentID)) {
        if (parentInfo->primaryTrackID >= 0) {
          info.primaryTrackID = parentInfo->primaryTrackID;
        }
        info.secondarySpecies = parentInfo->species;
        info.secondaryOriginPosition = parentInfo->originPosition;
        info.secondaryOriginEnergy = parentInfo->originEnergy;
      }
    }

    fEventAction->RecordPhotonCreationInfo(trackID, info);
  }
}
