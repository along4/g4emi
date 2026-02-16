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

  /// Sensor X length (0 means inherit scintillator X).
  G4double GetSensorX() const;
  /// Sensor Y length (0 means inherit scintillator Y).
  G4double GetSensorY() const;
  /// Sensor Z thickness.
  G4double GetSensorThickness() const;

  /// Sensor center X position in world coordinates.
  /// If unset, geometry code aligns sensor X with scintillator center X.
  G4double GetSensorPosX() const;
  /// Sensor center Y position in world coordinates.
  /// If unset, geometry code aligns sensor Y with scintillator center Y.
  G4double GetSensorPosY() const;
  /// Sensor center Z position in world coordinates.
  /// If unset, geometry code uses default flush placement on scintillator +Z face.
  G4double GetSensorPosZ() const;

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

  /// Set sensor X length.
  void SetSensorX(G4double value);
  /// Set sensor Y length.
  void SetSensorY(G4double value);
  /// Set sensor Z thickness.
  void SetSensorThickness(G4double value);

  /// Set sensor center X position in world coordinates.
  void SetSensorPosX(G4double value);
  /// Set sensor center Y position in world coordinates.
  void SetSensorPosY(G4double value);
  /// Set sensor center Z position in world coordinates.
  void SetSensorPosZ(G4double value);

  /// Get scintillator material name.
  std::string GetScintMaterial() const;
  /// Set scintillator material name.
  void SetScintMaterial(const std::string& value);

  /// Get output base filename/path (without output-format extension).
  std::string GetOutputFilename() const;
  /// Set output base filename/path (extension, if provided, is normalized away).
  void SetOutputFilename(const std::string& value);

  /// Get optional run name used to place outputs under `data/<runname>/`.
  std::string GetOutputRunName() const;
  /// Set optional run name (empty string disables run-specific subdirectory).
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

  /// Sensor dimensions in Geant4 internal units.
  /// `fSensorX`/`fSensorY` may be zero to indicate "inherit scintillator size".
  G4double fSensorX = 0.0;
  G4double fSensorY = 0.0;
  G4double fSensorThickness = 0.0;

  /// Sensor center position in world coordinates.
  /// Values may be NaN to indicate "use default alignment/placement behavior".
  G4double fSensorPosX = 0.0;
  G4double fSensorPosY = 0.0;
  G4double fSensorPosZ = 0.0;

  /// Material and output settings.
  std::string fScintMaterial;
  std::string fOutputFilename;
  std::string fOutputRunName;
};

#endif
