#ifndef TrackingAction_h
#define TrackingAction_h 1

#include "G4UserTrackingAction.hh"

class EventAction;
class G4Track;

/// Per-track hook that records ancestry/origin metadata before tracking starts.
class TrackingAction : public G4UserTrackingAction {
 public:
  /// `eventAction` receives all collected track/photon context.
  explicit TrackingAction(EventAction* eventAction);
  ~TrackingAction() override = default;

  /// Called by Geant4 for each new track at tracking start.
  void PreUserTrackingAction(const G4Track* track) override;

 private:
  /// Event-level metadata cache/write target.
  EventAction* fEventAction = nullptr;
};

#endif
