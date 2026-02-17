#ifndef config_h
#define config_h 1

#include "globals.hh"

#include <mutex>
#include <string>

/// Thread-safe runtime configuration shared across geometry/actions/messenger.
class Config {
 public:
  /// Supported output serialization modes.
  enum class OutputFormat { kCsv, kHdf5, kBoth };

  /// Initialize defaults (geometry, material, output mode/paths).
  Config();
  ~Config() = default;

  /// Get current output mode.
  OutputFormat GetOutputFormat() const;
  /// Parse and set output mode from text token (csv/hdf5/both).
  bool SetOutputFormat(const std::string& value);
  /// Set output mode directly.
  void SetOutputFormat(OutputFormat value);

  /// Parse output-mode text token into enum.
  static bool ParseOutputFormat(std::string value, OutputFormat* out);
  /// Convert output-mode enum to canonical string token.
  static const char* OutputFormatToString(OutputFormat value);

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
  /// Circular aperture radius at scintillator +Z face (0 disables aperture).
  G4double GetApertureRadius() const;

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
  /// Set circular aperture radius at scintillator +Z face (0 disables aperture).
  void SetApertureRadius(G4double value);

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

  /// Get CSV output file path derived from output settings.
  std::string GetCsvFilePath() const;
  /// Get HDF5 output file path derived from output settings.
  std::string GetHdf5FilePath() const;

 private:
  /// Guards all mutable config fields for cross-thread read/write safety.
  mutable std::mutex fMutex;

  /// Selected output format.
  OutputFormat fOutputFormat = OutputFormat::kCsv;

  /// Scintillator dimensions in Geant4 internal units.
  G4double fScintX = 0.0;
  G4double fScintY = 0.0;
  G4double fScintZ = 0.0;

  /// Scintillator center position in world coordinates.
  G4double fScintPosX = 0.0;
  G4double fScintPosY = 0.0;
  G4double fScintPosZ = 0.0;
  /// Circular pass-through radius for aperture at scintillator +Z face.
  G4double fApertureRadius = 0.0;

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
  std::string fOutputFilename;
  std::string fOutputPath;
  std::string fOutputRunName;
};

#endif
