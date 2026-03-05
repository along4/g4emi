#ifndef config_h
#define config_h 1

#include "globals.hh"

#include <array>
#include <mutex>
#include <string>
#include <vector>

/// Thread-safe runtime configuration shared across geometry/actions/messenger.
class Config {
 public:
  /// Initialize defaults (geometry, material, and output paths).
  Config();
  ~Config() = default;

  /// Scintillator X length.
  G4double GetScintX() const;
  /// Scintillator Y length.
  G4double GetScintY() const;
  /// Scintillator Z thickness.
  G4double GetScintZ() const;

  /// Scintillator center X position in world coordinates.
  G4double GetScintPosX() const;
  /// Scintillator center Y position in world coordinates.
  G4double GetScintPosY() const;
  /// Scintillator center Z position in world coordinates.
  G4double GetScintPosZ() const;
  /// Circular mask pass-through radius at scintillator +Z face (0 disables mask).
  G4double GetMaskRadius() const;

  /// Optical-interface X length (0 means inherit scintillator X).
  G4double GetOpticalInterfaceX() const;
  /// Optical-interface Y length (0 means inherit scintillator Y).
  G4double GetOpticalInterfaceY() const;
  /// Optical-interface Z thickness.
  G4double GetOpticalInterfaceThickness() const;

  /// Optical-interface center X position in world coordinates.
  /// If unset, geometry code aligns optical-interface X with scintillator center X.
  G4double GetOpticalInterfacePosX() const;
  /// Optical-interface center Y position in world coordinates.
  /// If unset, geometry code aligns optical-interface Y with scintillator center Y.
  G4double GetOpticalInterfacePosY() const;
  /// Optical-interface center Z position in world coordinates.
  /// If unset, geometry code uses default flush placement on scintillator +Z face.
  G4double GetOpticalInterfacePosZ() const;

  /// Set scintillator X length.
  void SetScintX(G4double value);
  /// Set scintillator Y length.
  void SetScintY(G4double value);
  /// Set scintillator Z thickness.
  void SetScintZ(G4double value);

  /// Set scintillator center X position in world coordinates.
  void SetScintPosX(G4double value);
  /// Set scintillator center Y position in world coordinates.
  void SetScintPosY(G4double value);
  /// Set scintillator center Z position in world coordinates.
  void SetScintPosZ(G4double value);
  /// Set circular mask pass-through radius at scintillator +Z face (0 disables mask).
  void SetMaskRadius(G4double value);

  /// Set optical-interface X length.
  void SetOpticalInterfaceX(G4double value);
  /// Set optical-interface Y length.
  void SetOpticalInterfaceY(G4double value);
  /// Set optical-interface Z thickness.
  void SetOpticalInterfaceThickness(G4double value);

  /// Set optical-interface center X position in world coordinates.
  void SetOpticalInterfacePosX(G4double value);
  /// Set optical-interface center Y position in world coordinates.
  void SetOpticalInterfacePosY(G4double value);
  /// Set optical-interface center Z position in world coordinates.
  void SetOpticalInterfacePosZ(G4double value);

  /// Get scintillator material name.
  std::string GetScintMaterial() const;
  /// Set scintillator material name.
  void SetScintMaterial(const std::string& value);

  /// Get scintillator density in Geant4 internal units.
  G4double GetScintDensity() const;
  /// Set scintillator density in Geant4 internal units.
  void SetScintDensity(G4double value);
  /// Get scintillator stoichiometric carbon atom count.
  G4int GetScintCarbonAtoms() const;
  /// Set scintillator stoichiometric carbon atom count.
  void SetScintCarbonAtoms(G4int value);
  /// Get scintillator stoichiometric hydrogen atom count.
  G4int GetScintHydrogenAtoms() const;
  /// Set scintillator stoichiometric hydrogen atom count.
  void SetScintHydrogenAtoms(G4int value);

  /// Get scintillator photon-energy nodes in Geant4 internal units.
  std::vector<G4double> GetScintPhotonEnergy() const;
  /// Set scintillator photon-energy nodes in Geant4 internal units.
  void SetScintPhotonEnergy(const std::vector<G4double>& values);
  /// Get scintillator refractive-index table values.
  std::vector<G4double> GetScintRIndex() const;
  /// Set scintillator refractive-index table values.
  void SetScintRIndex(const std::vector<G4double>& values);
  /// Get scintillator absorption-length values in Geant4 internal units.
  std::vector<G4double> GetScintAbsLength() const;
  /// Set scintillator absorption-length values in Geant4 internal units.
  void SetScintAbsLength(const std::vector<G4double>& values);
  /// Get scintillator emission-spectrum table values.
  std::vector<G4double> GetScintSpectrum() const;
  /// Set scintillator emission-spectrum table values.
  void SetScintSpectrum(const std::vector<G4double>& values);

  /// Get scintillation yield in photons/MeV.
  G4double GetScintYield() const;
  /// Set scintillation yield in photons/MeV.
  void SetScintYield(G4double value);
  /// Get scintillation resolution scale.
  G4double GetScintResolutionScale() const;
  /// Set scintillation resolution scale.
  void SetScintResolutionScale(G4double value);
  /// Get one scintillation decay time constant by 1-based component index.
  G4double GetScintTimeConstant(G4int componentIndex) const;
  /// Set one scintillation decay time constant by 1-based component index.
  void SetScintTimeConstant(G4int componentIndex, G4double value);
  /// Get one scintillation yield fraction by 1-based component index.
  G4double GetScintYieldFraction(G4int componentIndex) const;
  /// Set one scintillation yield fraction by 1-based component index.
  void SetScintYieldFraction(G4int componentIndex, G4double value);
  /// Get scintillation decay time in Geant4 internal units.
  /// Compatibility wrapper for component 1.
  G4double GetScintTimeConstant() const;
  /// Set scintillation decay time in Geant4 internal units.
  /// Compatibility wrapper for component 1.
  void SetScintTimeConstant(G4double value);
  /// Get SCINTILLATIONYIELD1 component fraction.
  /// Compatibility wrapper for component 1.
  G4double GetScintYield1() const;
  /// Set SCINTILLATIONYIELD1 component fraction.
  /// Compatibility wrapper for component 1.
  void SetScintYield1(G4double value);

  /// Get monotonic material revision; increments when scintillator properties change.
  G4int GetScintMaterialVersion() const;

  /// Get output base filename/path (without output-format extension).
  std::string GetOutputFilename() const;
  /// Set output base filename/path (extension, if provided, is normalized away).
  void SetOutputFilename(const std::string& value);

  /// Get optional output directory path used to place output files.
  std::string GetOutputPath() const;
  /// Set optional output directory path (empty clears explicit path override).
  void SetOutputPath(const std::string& value);

  /// Get optional run name used to place outputs under a run-specific subdirectory.
  std::string GetOutputRunName() const;
  /// Set optional run name (empty string disables run-specific subdirectory).
  /// With output-path override set, run outputs go under
  /// `<outputPath>/<runName>/simulatedPhotons/`.
  /// Without output-path override, run outputs go under
  /// `data/<runName>/simulatedPhotons/`.
  void SetOutputRunName(const std::string& value);

  /// Get HDF5 output file path derived from output settings.
  std::string GetHdf5FilePath() const;

 private:
  /// Guards all mutable config fields for cross-thread read/write safety.
  mutable std::mutex fMutex;

  /// Scintillator dimensions in Geant4 internal units.
  G4double fScintX = 0.0;
  G4double fScintY = 0.0;
  G4double fScintZ = 0.0;

  /// Scintillator center position in world coordinates.
  G4double fScintPosX = 0.0;
  G4double fScintPosY = 0.0;
  G4double fScintPosZ = 0.0;
  /// Circular pass-through radius for mask at scintillator +Z face.
  G4double fMaskRadius = 0.0;

  /// Optical-interface dimensions in Geant4 internal units.
  /// `fOpticalInterfaceX`/`fOpticalInterfaceY` may be zero to indicate "inherit scintillator size".
  G4double fOpticalInterfaceX = 0.0;
  G4double fOpticalInterfaceY = 0.0;
  G4double fOpticalInterfaceThickness = 0.0;

  /// Optical-interface center position in world coordinates.
  /// Values may be NaN to indicate "use default alignment/placement behavior".
  G4double fOpticalInterfacePosX = 0.0;
  G4double fOpticalInterfacePosY = 0.0;
  G4double fOpticalInterfacePosZ = 0.0;

  /// Material and output settings.
  std::string fScintMaterial;
  G4double fScintDensity = 0.0;
  G4int fScintCarbonAtoms = 0;
  G4int fScintHydrogenAtoms = 0;
  std::vector<G4double> fScintPhotonEnergy;
  std::vector<G4double> fScintRIndex;
  std::vector<G4double> fScintAbsLength;
  std::vector<G4double> fScintSpectrum;
  G4double fScintYield = 0.0;
  G4double fScintResolutionScale = 1.0;
  std::array<G4double, 3> fScintTimeConstants = {0.0, 0.0, 0.0};
  std::array<G4double, 3> fScintYieldFractions = {1.0, 0.0, 0.0};
  G4int fScintMaterialVersion = 0;
  std::string fOutputFilename;
  std::string fOutputPath;
  std::string fOutputRunName;
};

#endif
