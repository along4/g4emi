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
#include "G4VPhysicalVolume.hh"

/**
 * SteppingAction processes each transport step and records information that is
 * naturally available only at stepping time.
 *
 * In this application:
 * - accumulate deposited energy in the scintillator scoring volume,
 * - capture positions of newly created optical-photon secondaries so tracking
 *   callbacks can later attach creation-point metadata consistently.
 */
SteppingAction::SteppingAction(const DetectorConstruction* detector,
                               EventAction* eventAction)
    : fDetector(detector), fEventAction(eventAction) {}

/**
 * Called by Geant4 for every simulation step.
 *
 * Processing is intentionally restricted to the configured scintillator scoring
 * volume to avoid collecting irrelevant data from world/optical-interface regions.
 */
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

  auto* logicalVolume = volume->GetLogicalVolume();
  if (logicalVolume != fDetector->GetScoringVolume()) {
    return;
  }

  // Accumulate per-event energy deposition in scintillator.
  const auto edep = step->GetTotalEnergyDeposit();
  if (edep > 0.0) {
    fEventAction->AddEdep(edep);
  }

  // Capture optical-photon exit point when crossing out of scintillator at a
  // geometry boundary. This does not require an additional sensitive detector.
  const auto* track = step->GetTrack();
  const auto* postStepPoint = step->GetPostStepPoint();
  if (track && postStepPoint &&
      track->GetParticleDefinition() ==
          G4OpticalPhoton::OpticalPhotonDefinition() &&
      postStepPoint->GetStepStatus() == fGeomBoundary) {
    const auto* postVolume = postStepPoint->GetTouchableHandle()->GetVolume();
    const auto* postLogicalVolume =
        postVolume ? postVolume->GetLogicalVolume() : nullptr;
    if (postLogicalVolume != logicalVolume) {
      fEventAction->RecordPhotonScintillatorExit(track->GetTrackID(),
                                                 postStepPoint->GetPosition());
    }
  }

  // Record optical photons spawned in this step. We store their creation
  // position keyed by track pointer, then TrackingAction consumes it when the
  // new secondary track enters PreUserTrackingAction.
  const auto* secondaries = step->GetSecondaryInCurrentStep();
  if (!secondaries || secondaries->empty()) {
    return;
  }

  for (const auto* secondary : *secondaries) {
    if (!secondary ||
        secondary->GetParticleDefinition() !=
            G4OpticalPhoton::OpticalPhotonDefinition()) {
      continue;
    }

    fEventAction->RecordPendingPhotonOrigin(secondary, secondary->GetPosition());
  }
}
