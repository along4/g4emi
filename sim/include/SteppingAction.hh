#ifndef SteppingAction_h
#define SteppingAction_h 1

#include "G4UserSteppingAction.hh"

class DetectorConstruction;
class EventAction;
class G4Step;

/// Per-step hook for scoring deposition and capturing new optical secondaries.
class SteppingAction : public G4UserSteppingAction {
 public:
  /// Requires detector/scoring-volume access plus event-level accumulator.
  SteppingAction(const DetectorConstruction* detector, EventAction* eventAction);
  ~SteppingAction() override = default;

  /// Called each transport step; filtered to scintillator scoring volume.
  void UserSteppingAction(const G4Step* step) override;

 private:
  /// Geometry access (especially scoring volume pointer).
  const DetectorConstruction* fDetector = nullptr;
  /// Event-local state sink.
  EventAction* fEventAction = nullptr;
};

#endif
