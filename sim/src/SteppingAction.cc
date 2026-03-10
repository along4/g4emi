#include "SteppingAction.hh"

#include "DetectorConstruction.hh"
#include "EventAction.hh"

#include "G4LogicalVolume.hh"
#include "G4OpticalPhoton.hh"
#include "G4Step.hh"
#include "G4StepPoint.hh"
#include "G4StepStatus.hh"
#include "G4Track.hh"
#include "G4TouchableHandle.hh"
#include "G4VProcess.hh"
#include "G4VPhysicalVolume.hh"

namespace {
bool IsInteractionProcess(const G4VProcess* process) {
  if (!process) {
    return false;
  }
  const auto& processName = process->GetProcessName();
  return processName != "Transportation" && processName != "CoupledTransportation";
}

G4int ResolvePrimaryTrackID(const G4Track* track, const EventAction* eventAction) {
  if (!track || !eventAction) {
    return -1;
  }
  if (track->GetParentID() == 0) {
    return track->GetTrackID();
  }
  if (const auto* trackInfo = eventAction->FindTrackInfo(track->GetTrackID())) {
    return trackInfo->primaryTrackID;
  }
  return -1;
}
}  // namespace

SteppingAction::SteppingAction(const DetectorConstruction* detector,
                               EventAction* eventAction)
    : fDetector(detector), fEventAction(eventAction) {}

void SteppingAction::UserSteppingAction(const G4Step* step) {
  if (!step || !fEventAction || !fDetector) {
    return;
  }

  const auto* preStepPoint = step->GetPreStepPoint();
  if (!preStepPoint) {
    return;
  }

  const auto* volume = preStepPoint->GetTouchableHandle()->GetVolume();
  if (!volume) {
    return;
  }

  auto* preLogicalVolume = volume->GetLogicalVolume();
  if (preLogicalVolume != fDetector->GetScoringVolume()) {
    return;
  }

  const auto* track = step->GetTrack();
  const auto* postStepPoint = step->GetPostStepPoint();
  const auto* opticalPhoton = G4OpticalPhoton::OpticalPhotonDefinition();

  if (track && postStepPoint && track->GetParentID() == 0) {
    if (IsInteractionProcess(postStepPoint->GetProcessDefinedStep())) {
      fEventAction->RecordPrimaryScintillatorFirstInteraction(
          track->GetTrackID(), postStepPoint->GetGlobalTime());
    }
  }

  if (track && postStepPoint &&
      track->GetParticleDefinition() == opticalPhoton &&
      postStepPoint->GetStepStatus() == fGeomBoundary) {
    const auto* postVolume = postStepPoint->GetTouchableHandle()->GetVolume();
    const auto* postLogicalVolume =
        postVolume ? postVolume->GetLogicalVolume() : nullptr;
    if (postLogicalVolume != preLogicalVolume) {
      fEventAction->RecordPhotonScintillatorExit(track->GetTrackID(),
                                                 postStepPoint->GetPosition());
    }
  }

  if (track && postStepPoint && track->GetParentID() > 0 &&
      track->GetParticleDefinition() != opticalPhoton) {
    fEventAction->RecordSecondaryScintillatorEndpoint(track->GetTrackID(),
                                                      postStepPoint->GetPosition());
  }

  const auto* secondaries = step->GetSecondaryInCurrentStep();
  if (!secondaries || secondaries->empty()) {
    return;
  }

  const G4int primaryTrackID = ResolvePrimaryTrackID(track, fEventAction);

  for (const auto* secondary : *secondaries) {
    if (!secondary) {
      continue;
    }
    const G4bool isOpticalPhoton = secondary->GetParticleDefinition() == opticalPhoton;
    fEventAction->RecordPrimarySecondaryCreation(primaryTrackID, isOpticalPhoton);
    if (!isOpticalPhoton) {
      continue;
    }

    fEventAction->RecordPendingPhotonOrigin(secondary, secondary->GetPosition());
  }
}
