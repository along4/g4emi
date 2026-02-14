#include "SteppingAction.hh"

#include "DetectorConstruction.hh"
#include "EventAction.hh"

#include "G4LogicalVolume.hh"
#include "G4OpticalPhoton.hh"
#include "G4Step.hh"
#include "G4StepPoint.hh"
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
 * volume to avoid collecting irrelevant data from world/sensor regions.
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
