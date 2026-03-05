#include "PhotonOpticalInterfaceSD.hh"

#include "EventAction.hh"

#include "G4OpticalPhoton.hh"
#include "G4PhysicalConstants.hh"
#include "G4Step.hh"
#include "G4StepPoint.hh"
#include "G4Track.hh"
#include "G4TrackStatus.hh"

namespace {
void FillPrimaryContext(EventAction* eventAction, EventAction::PhotonHitRecord* hit) {
  hit->primarySpecies = eventAction->GetPrimarySpecies();
  hit->primaryX = eventAction->GetPrimaryPosition().x();
  hit->primaryY = eventAction->GetPrimaryPosition().y();
}

void FillOpticalInterfaceContext(const G4StepPoint* preStep,
                                 EventAction::PhotonHitRecord* hit) {
  hit->opticalInterfaceHitPosition = preStep->GetPosition();
  hit->opticalInterfaceHitTime = preStep->GetGlobalTime();
  hit->opticalInterfaceHitDirection = preStep->GetMomentumDirection();
  hit->opticalInterfaceHitPolarization = preStep->GetPolarization();
  hit->photonCreationTime = preStep->GetGlobalTime() - preStep->GetLocalTime();
  hit->opticalInterfaceHitEnergy = preStep->GetTotalEnergy();

  if (hit->opticalInterfaceHitEnergy > 0.0) {
    hit->opticalInterfaceHitWavelength = (h_Planck * c_light) / hit->opticalInterfaceHitEnergy;
  }
}

void FillAncestryContext(EventAction* eventAction,
                         const G4Track* track,
                         EventAction::PhotonHitRecord* hit) {
  if (const auto* creationInfo = eventAction->FindPhotonCreationInfo(track->GetTrackID())) {
    hit->primaryID = creationInfo->primaryTrackID;
    hit->secondaryID = creationInfo->secondaryTrackID;
    hit->secondarySpecies = creationInfo->secondarySpecies;
    hit->secondaryOriginPosition = creationInfo->secondaryOriginPosition;
    hit->secondaryOriginEnergy = creationInfo->secondaryOriginEnergy;
    hit->scintOriginPosition = creationInfo->scintOriginPosition;
    return;
  }

  if (const auto* trackInfo = eventAction->FindTrackInfo(track->GetTrackID())) {
    hit->primaryID = trackInfo->primaryTrackID;
  }
  hit->secondaryID = track->GetParentID();
  hit->secondarySpecies = "unknown";
  hit->secondaryOriginPosition = G4ThreeVector();
  hit->secondaryOriginEnergy = -1.0;
  hit->scintOriginPosition = track->GetVertexPosition();
}
}  // namespace

PhotonOpticalInterfaceSD::PhotonOpticalInterfaceSD(const G4String& name)
    : G4VSensitiveDetector(name) {}

G4bool PhotonOpticalInterfaceSD::ProcessHits(G4Step* step, G4TouchableHistory*) {
  if (!step) {
    return false;
  }

  auto* track = step->GetTrack();
  if (!track || track->GetParticleDefinition() != G4OpticalPhoton::OpticalPhotonDefinition()) {
    return false;
  }

  auto* eventAction = EventAction::Instance();
  if (!eventAction) {
    return false;
  }

  const auto* preStep = step->GetPreStepPoint();
  if (!preStep) {
    return false;
  }

  EventAction::PhotonHitRecord hit;
  hit.photonID = track->GetTrackID();
  FillPrimaryContext(eventAction, &hit);
  FillOpticalInterfaceContext(preStep, &hit);
  FillAncestryContext(eventAction, track, &hit);
  hit.hasPhotonScintExitPosition = eventAction->ConsumePhotonScintillatorExit(
      track->GetTrackID(), &hit.photonScintExitPosition);
  eventAction->RecordPhotonHit(hit);

  // One recorded hit per detected optical photon.
  track->SetTrackStatus(fStopAndKill);
  return true;
}
