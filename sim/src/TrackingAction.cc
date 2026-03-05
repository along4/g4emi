#include "TrackingAction.hh"

#include "EventAction.hh"

#include "G4ParticleDefinition.hh"
#include "G4Track.hh"

#include <string>

namespace {
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

G4int ResolvePrimaryTrackID(const G4Track* track, EventAction* eventAction) {
  if (!track || !eventAction) {
    return -1;
  }
  if (track->GetParentID() == 0) {
    return track->GetTrackID();
  }
  if (const auto* parentInfo = eventAction->FindTrackInfo(track->GetParentID())) {
    return parentInfo->primaryTrackID;
  }
  return -1;
}

bool IsOpticalPhoton(const G4String& particleName) {
  return particleName == "opticalphoton";
}
}  // namespace

TrackingAction::TrackingAction(EventAction* eventAction)
    : fEventAction(eventAction) {}

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
  trackInfo.primaryTrackID = ResolvePrimaryTrackID(track, fEventAction);
  fEventAction->RecordTrackInfo(trackID, trackInfo);

  if (IsOpticalPhoton(particleName)) {
    EventAction::PhotonCreationInfo info;
    info.primaryTrackID = trackInfo.primaryTrackID;
    info.secondaryTrackID = parentID;
    info.scintOriginPosition = track->GetVertexPosition();

    // Prefer stepping-recorded creation point when available.
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
