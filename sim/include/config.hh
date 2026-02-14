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
  /// Back-face sensor thickness.
  G4double GetSensorThickness() const;

  /// Set scintillator X length.
  void SetScintX(G4double value);
  /// Set scintillator Y length.
  void SetScintY(G4double value);
  /// Set scintillator Z thickness.
  void SetScintZ(G4double value);
  /// Set back-face sensor thickness.
  void SetSensorThickness(G4double value);

  /// Get scintillator material name.
  std::string GetScintMaterial() const;
  /// Set scintillator material name.
  void SetScintMaterial(const std::string& value);

  /// Get output base filename/path (without output-format extension).
  std::string GetOutputFilename() const;
  /// Set output base filename/path (extension, if provided, is normalized away).
  void SetOutputFilename(const std::string& value);
  /// Get CSV output file path derived from output base filename.
  std::string GetCsvFilePath() const;
  /// Get HDF5 output file path derived from output base filename.
  std::string GetHdf5FilePath() const;

 private:
  /// Guards all mutable config fields for cross-thread read/write safety.
  mutable std::mutex fMutex;

  /// Selected output format.
  OutputFormat fOutputFormat = OutputFormat::kCsv;

  /// Scintillator dimensions and sensor thickness in Geant4 internal units.
  G4double fScintX = 0.0;
  G4double fScintY = 0.0;
  G4double fScintZ = 0.0;
  G4double fSensorThickness = 0.0;

  /// Material and output settings.
  std::string fScintMaterial;
  std::string fOutputFilename;
};

#endif
