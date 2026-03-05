#ifndef TrackingAction_h
#define TrackingAction_h 1

#include "G4UserTrackingAction.hh"

class EventAction;
class G4Track;

/// Per-track hook that records ancestry/origin metadata at track start.
class TrackingAction : public G4UserTrackingAction {
 public:
  /// `eventAction` receives track and photon creation context.
  explicit TrackingAction(EventAction* eventAction);
  ~TrackingAction() override = default;

  /// Called by Geant4 before each track is processed.
  void PreUserTrackingAction(const G4Track* track) override;

 private:
  /// Event-local sink for per-track metadata.
  EventAction* fEventAction = nullptr;
};

#endif
