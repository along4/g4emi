#ifndef DetectorConstruction_h
#define DetectorConstruction_h 1

#include "G4VUserDetectorConstruction.hh"

class Config;
class G4LogicalVolume;
class G4VPhysicalVolume;

/// Builds detector geometry, materials, and sensitive-detector assignment.
class DetectorConstruction : public G4VUserDetectorConstruction {
 public:
  /// Uses shared `Config` values to parameterize geometry/materials.
  explicit DetectorConstruction(const Config* config);
  ~DetectorConstruction() override = default;

  /// Build and return world physical volume.
  G4VPhysicalVolume* Construct() override;
  /// Register sensitive detector(s) after geometry creation.
  void ConstructSDandField() override;
  /// Scintillator logical volume used as the stepping-action scoring region.
  G4LogicalVolume* GetScoringVolume() const { return fScoringVolume; }

 private:
  /// Read-only runtime configuration source.
  const Config* fConfig = nullptr;
  /// Logical volume for scintillator energy-deposition scoring.
  G4LogicalVolume* fScoringVolume = nullptr;
  /// Logical volume for optical-photon hit detection plane.
  G4LogicalVolume* fPhotonSensorVolume = nullptr;
};

#endif
