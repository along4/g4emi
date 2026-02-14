#ifndef ActionInitialization_h
#define ActionInitialization_h 1

#include "G4VUserActionInitialization.hh"

class DetectorConstruction;
class Config;

/// Registers Geant4 user action classes used during each run.
class ActionInitialization : public G4VUserActionInitialization {
 public:
  /// `detector` and `config` are shared read-only dependencies for actions.
  ActionInitialization(const DetectorConstruction* detector, const Config* config);
  ~ActionInitialization() override = default;

  /// Construct per-thread action instances (generator, event, stepping, tracking).
  void Build() const override;

 private:
  /// Detector access for stepping action configuration.
  const DetectorConstruction* fDetector = nullptr;
  /// Global run configuration (output mode, geometry settings, etc.).
  const Config* fConfig = nullptr;
};

#endif
