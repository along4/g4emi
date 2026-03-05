#ifndef ActionInitialization_h
#define ActionInitialization_h 1

#include "G4VUserActionInitialization.hh"

class DetectorConstruction;
class Config;

/// Registers Geant4 user action classes used during each run.
class ActionInitialization : public G4VUserActionInitialization {
 public:
  /// `detector` and `config` are shared read-only action dependencies.
  ActionInitialization(const DetectorConstruction* detector, const Config* config);
  ~ActionInitialization() override = default;

  /// Register worker-thread actions.
  void Build() const override;
  /// Register master-thread actions.
  void BuildForMaster() const override;

 private:
  /// Detector reference used to configure stepping action.
  const DetectorConstruction* fDetector = nullptr;
  /// Global runtime configuration.
  const Config* fConfig = nullptr;
};

#endif
