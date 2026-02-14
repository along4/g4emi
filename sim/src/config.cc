#include "config.hh"
#include "SimIO.hh"
#include "utils.hh"

#include "G4SystemOfUnits.hh"

/**
 * Construct simulation defaults used when no UI command overrides are provided.
 *
 * Defaults are intentionally conservative and mirror the original hard-coded
 * application setup:
 * - Geometry: 5x5x1 cm scintillator with a 0.1 mm sensor plane.
 * - Material: EJ200.
 * - Output: CSV mode (enum default in header), output base name
 *   "data/photon_sensor_hits", and no run-name subdirectory.
 */
Config::Config()
    : fScintX(5.0 * cm),
      fScintY(5.0 * cm),
      fScintZ(1.0 * cm),
      fSensorThickness(0.1 * mm),
      fScintMaterial("EJ200"),
      fOutputFilename("data/photon_sensor_hits"),
      fOutputRunName("") {}

/**
 * Thread-safe getter for output mode.
 *
 * Access is locked because this object is shared across components and may be
 * read from event-processing code while UI commands are applied.
 */
Config::OutputFormat Config::GetOutputFormat() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fOutputFormat;
}

/**
 * Parse and set output mode from user text.
 *
 * Returns:
 * - true: recognized value and internal mode updated.
 * - false: value is invalid and state is unchanged.
 */
bool Config::SetOutputFormat(const std::string& value) {
  OutputFormat parsed = OutputFormat::kCsv;
  if (!ParseOutputFormat(value, &parsed)) {
    return false;
  }
  SetOutputFormat(parsed);
  return true;
}

/// Thread-safe setter overload for already-parsed enum values.
void Config::SetOutputFormat(OutputFormat value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fOutputFormat = value;
}

/**
 * Convert UI text into OutputFormat enum.
 *
 * Accepted tokens:
 * - "csv"
 * - "hdf5" or "h5"
 * - "both"
 *
 * This method is pure parsing: it does not mutate Config state.
 */
bool Config::ParseOutputFormat(std::string value, OutputFormat* out) {
  if (!out) {
    return false;
  }

  value = Utils::ToLower(value);
  if (value == "csv") {
    *out = OutputFormat::kCsv;
    return true;
  }
  if (value == "hdf5" || value == "h5") {
    *out = OutputFormat::kHdf5;
    return true;
  }
  if (value == "both") {
    *out = OutputFormat::kBoth;
    return true;
  }
  return false;
}

/**
 * Convert OutputFormat enum to canonical UI/storage text.
 *
 * The fallback return ("csv") protects against undefined enum values if the
 * code is extended in the future and this switch is not updated.
 */
const char* Config::OutputFormatToString(OutputFormat value) {
  switch (value) {
    case OutputFormat::kCsv:
      return "csv";
    case OutputFormat::kHdf5:
      return "hdf5";
    case OutputFormat::kBoth:
      return "both";
  }
  return "csv";
}

/// Thread-safe geometry getter: scintillator size in X (Geant4 internal units).
G4double Config::GetScintX() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintX;
}

/// Thread-safe geometry getter: scintillator size in Y.
G4double Config::GetScintY() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintY;
}

/// Thread-safe geometry getter: scintillator size in Z (thickness).
G4double Config::GetScintZ() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintZ;
}

/// Thread-safe geometry getter: sensor thickness.
G4double Config::GetSensorThickness() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fSensorThickness;
}

/// Thread-safe geometry setter: scintillator size in X.
void Config::SetScintX(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fScintX = value;
}

/// Thread-safe geometry setter: scintillator size in Y.
void Config::SetScintY(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fScintY = value;
}

/// Thread-safe geometry setter: scintillator size in Z.
void Config::SetScintZ(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fScintZ = value;
}

/// Thread-safe geometry setter: sensor thickness.
void Config::SetSensorThickness(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fSensorThickness = value;
}

/// Thread-safe material-name getter.
std::string Config::GetScintMaterial() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintMaterial;
}

/**
 * Set scintillator material name.
 *
 * Empty strings are ignored to prevent accidental erasure from malformed macro
 * lines or empty UI arguments.
 */
void Config::SetScintMaterial(const std::string& value) {
  if (value.empty()) {
    return;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  fScintMaterial = value;
}

/// Thread-safe getter for output base filename/path.
std::string Config::GetOutputFilename() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fOutputFilename;
}

/**
 * Set output base filename/path.
 *
 * If the user passes a recognized output extension (.csv/.h5/.hdf5), that
 * extension is removed so format-specific getters can append the selected
 * canonical extension.
 */
void Config::SetOutputFilename(const std::string& value) {
  if (value.empty()) {
    return;
  }

  const std::string normalized = SimIO::StripKnownOutputExtension(value);
  if (normalized.empty()) {
    return;
  }

  std::lock_guard<std::mutex> lock(fMutex);
  fOutputFilename = normalized;
}

/// Thread-safe getter for output run name.
std::string Config::GetOutputRunName() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fOutputRunName;
}

/**
 * Set optional run-name output directory.
 *
 * An empty value clears run-name routing. Non-empty values are normalized so
 * they map to exactly one directory under `data/`.
 */
void Config::SetOutputRunName(const std::string& value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fOutputRunName = SimIO::NormalizeRunName(value);
}

/// Thread-safe getter for CSV output path derived from output settings.
std::string Config::GetCsvFilePath() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return SimIO::ComposeOutputPath(fOutputFilename, fOutputRunName, ".csv");
}

/// Thread-safe getter for HDF5 output path derived from output settings.
std::string Config::GetHdf5FilePath() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return SimIO::ComposeOutputPath(fOutputFilename, fOutputRunName, ".h5");
}
