#include "ActionInitialization.hh"

#include "DetectorConstruction.hh"
#include "EventAction.hh"
#include "PrimaryGeneratorAction.hh"
#include "RunAction.hh"
#include "SteppingAction.hh"
#include "TrackingAction.hh"

ActionInitialization::ActionInitialization(const DetectorConstruction* detector,
                                           const Config* config)
    : fDetector(detector), fConfig(config) {}

void ActionInitialization::Build() const {
  SetUserAction(new RunAction(fConfig));
  SetUserAction(new PrimaryGeneratorAction());

  auto* eventAction = new EventAction(fConfig);
  SetUserAction(eventAction);

  SetUserAction(new SteppingAction(fDetector, eventAction));
  SetUserAction(new TrackingAction(eventAction));
}

void ActionInitialization::BuildForMaster() const {
  SetUserAction(new RunAction(fConfig));
}
