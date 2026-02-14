#include "PhotonSensorSD.hh"

#include "EventAction.hh"

#include "G4OpticalPhoton.hh"
#include "G4ParticleDefinition.hh"
#include "G4Step.hh"
#include "G4StepPoint.hh"
#include "G4Track.hh"
#include "G4TrackStatus.hh"

PhotonSensorSD::PhotonSensorSD(const G4String& name) : G4VSensitiveDetector(name) {}

G4bool PhotonSensorSD::ProcessHits(G4Step* step, G4TouchableHistory*) {
  if (!step) {
    return false;
  }

  auto* track = step->GetTrack();
  if (!track ||
      track->GetParticleDefinition() != G4OpticalPhoton::OpticalPhotonDefinition()) {
    return false;
  }

  auto* eventAction = EventAction::Instance();
  if (!eventAction) {
    return false;
  }

  EventAction::PhotonHitRecord hit;
  hit.photonID = track->GetTrackID();
  hit.primarySpecies = eventAction->GetPrimarySpecies();
  hit.primaryX = eventAction->GetPrimaryPosition().x();
  hit.primaryY = eventAction->GetPrimaryPosition().y();
  hit.sensorHitPosition = step->GetPreStepPoint()->GetPosition();

  if (const auto* creationInfo =
          eventAction->FindPhotonCreationInfo(track->GetTrackID())) {
    hit.primaryID = creationInfo->primaryTrackID;
    hit.secondaryID = creationInfo->secondaryTrackID;
    hit.secondarySpecies = creationInfo->secondarySpecies;
    hit.secondaryOriginPosition = creationInfo->secondaryOriginPosition;
    hit.secondaryOriginEnergy = creationInfo->secondaryOriginEnergy;
    hit.scintOriginPosition = creationInfo->scintOriginPosition;
  } else {
    if (const auto* trackInfo = eventAction->FindTrackInfo(track->GetTrackID())) {
      hit.primaryID = trackInfo->primaryTrackID;
    }
    hit.secondaryID = track->GetParentID();
    hit.secondarySpecies = "unknown";
    hit.secondaryOriginPosition = G4ThreeVector();
    hit.secondaryOriginEnergy = -1.0;
    hit.scintOriginPosition = track->GetVertexPosition();
  }

  eventAction->RecordPhotonHit(hit);
  track->SetTrackStatus(fStopAndKill);
  return true;
}
