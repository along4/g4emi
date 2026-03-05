#ifndef DetectorConstruction_h
#define DetectorConstruction_h 1

#include "G4VUserDetectorConstruction.hh"

class Config;
class G4LogicalVolume;
class G4VPhysicalVolume;

/// Builds detector geometry/materials and assigns sensitive detectors.
class DetectorConstruction : public G4VUserDetectorConstruction {
 public:
  /// Parameterize geometry/materials from shared runtime config.
  explicit DetectorConstruction(const Config* config);
  ~DetectorConstruction() override = default;

  /// Build world and detector geometry.
  G4VPhysicalVolume* Construct() override;
  /// Register sensitive detector bindings after geometry creation.
  void ConstructSDandField() override;
  /// Scintillator logical volume used as the stepping-action scoring region.
  G4LogicalVolume* GetScoringVolume() const { return fScoringVolume; }

 private:
  /// Read-only runtime configuration source.
  const Config* fConfig = nullptr;
  /// Scintillator logical volume.
  G4LogicalVolume* fScoringVolume = nullptr;
  /// Optical-interface logical volume used for photon hit collection.
  G4LogicalVolume* fOpticalInterfaceVolume = nullptr;
};

#endif
