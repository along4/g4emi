#include "config.hh"
#include "SimIO.hh"
#include "utils.hh"

#include "G4SystemOfUnits.hh"

#include <filesystem>
#include <limits>

namespace {
constexpr G4int kScintillationComponentCount = 3;

bool IsValidScintillationComponentIndex(G4int componentIndex) {
  return componentIndex >= 1 && componentIndex <= kScintillationComponentCount;
}

std::size_t ToZeroBasedComponentIndex(G4int componentIndex) {
  return static_cast<std::size_t>(componentIndex - 1);
}
}  // namespace

// Initialize geometry, material, and output defaults.
Config::Config()
    : fScintX(5.0 * cm),
      fScintY(5.0 * cm),
      fScintZ(1.0 * cm),
      fScintPosX(0.0),
      fScintPosY(0.0),
      fScintPosZ(0.0),
      fMaskRadius(0.0),
      fOpticalInterfaceX(0.0),
      fOpticalInterfaceY(0.0),
      fOpticalInterfaceThickness(0.1 * mm),
      fOpticalInterfacePosX(std::numeric_limits<G4double>::quiet_NaN()),
      fOpticalInterfacePosY(std::numeric_limits<G4double>::quiet_NaN()),
      fOpticalInterfacePosZ(std::numeric_limits<G4double>::quiet_NaN()),
      fScintMaterial("EJ200"),
      fScintDensity(1.023 * g / cm3),
      fScintCarbonAtoms(9),
      fScintHydrogenAtoms(10),
      fScintPhotonEnergy({2.00 * eV, 2.40 * eV, 2.76 * eV, 3.10 * eV, 3.50 * eV}),
      fScintRIndex({1.58, 1.58, 1.58, 1.58, 1.58}),
      fScintAbsLength({380.0 * cm, 380.0 * cm, 380.0 * cm, 300.0 * cm, 220.0 * cm}),
      fScintSpectrum({0.05, 0.35, 1.00, 0.45, 0.08}),
      fScintYield(10000.0),
      fScintResolutionScale(1.0),
      fScintTimeConstants({2.1 * ns, 0.0, 0.0}),
      fScintYieldFractions({1.0, 0.0, 0.0}),
      fScintMaterialVersion(0),
      fOutputFilename("data/photon_optical_interface_hits"),
      fOutputPath(""),
      fOutputRunName("") {}

G4double Config::GetScintX() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintX;
}

G4double Config::GetScintY() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintY;
}

G4double Config::GetScintZ() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintZ;
}

G4double Config::GetScintPosX() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintPosX;
}

G4double Config::GetScintPosY() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintPosY;
}

G4double Config::GetScintPosZ() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintPosZ;
}

G4double Config::GetMaskRadius() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fMaskRadius;
}

G4double Config::GetOpticalInterfaceX() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fOpticalInterfaceX;
}

G4double Config::GetOpticalInterfaceY() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fOpticalInterfaceY;
}

G4double Config::GetOpticalInterfaceThickness() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fOpticalInterfaceThickness;
}

G4double Config::GetOpticalInterfacePosX() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fOpticalInterfacePosX;
}

G4double Config::GetOpticalInterfacePosY() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fOpticalInterfacePosY;
}

G4double Config::GetOpticalInterfacePosZ() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fOpticalInterfacePosZ;
}

void Config::SetScintX(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fScintX = value;
}

void Config::SetScintY(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fScintY = value;
}

void Config::SetScintZ(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fScintZ = value;
}

void Config::SetScintPosX(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fScintPosX = value;
}

void Config::SetScintPosY(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fScintPosY = value;
}

void Config::SetScintPosZ(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fScintPosZ = value;
}

void Config::SetMaskRadius(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fMaskRadius = value;
}

void Config::SetOpticalInterfaceX(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fOpticalInterfaceX = value;
}

void Config::SetOpticalInterfaceY(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fOpticalInterfaceY = value;
}

void Config::SetOpticalInterfaceThickness(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fOpticalInterfaceThickness = value;
}

void Config::SetOpticalInterfacePosX(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fOpticalInterfacePosX = value;
}

void Config::SetOpticalInterfacePosY(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fOpticalInterfacePosY = value;
}

void Config::SetOpticalInterfacePosZ(G4double value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fOpticalInterfacePosZ = value;
}

std::string Config::GetScintMaterial() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintMaterial;
}

void Config::SetScintMaterial(const std::string& value) {
  if (value.empty()) {
    return;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  fScintMaterial = value;
  ++fScintMaterialVersion;
}

G4double Config::GetScintDensity() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintDensity;
}

void Config::SetScintDensity(G4double value) {
  if (value <= 0.0) {
    return;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  fScintDensity = value;
  ++fScintMaterialVersion;
}

G4int Config::GetScintCarbonAtoms() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintCarbonAtoms;
}

void Config::SetScintCarbonAtoms(G4int value) {
  if (value <= 0) {
    return;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  fScintCarbonAtoms = value;
  ++fScintMaterialVersion;
}

G4int Config::GetScintHydrogenAtoms() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintHydrogenAtoms;
}

void Config::SetScintHydrogenAtoms(G4int value) {
  if (value <= 0) {
    return;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  fScintHydrogenAtoms = value;
  ++fScintMaterialVersion;
}

std::vector<G4double> Config::GetScintPhotonEnergy() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintPhotonEnergy;
}

void Config::SetScintPhotonEnergy(const std::vector<G4double>& values) {
  if (values.empty()) {
    return;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  fScintPhotonEnergy = values;
  ++fScintMaterialVersion;
}

std::vector<G4double> Config::GetScintRIndex() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintRIndex;
}

void Config::SetScintRIndex(const std::vector<G4double>& values) {
  if (values.empty()) {
    return;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  fScintRIndex = values;
  ++fScintMaterialVersion;
}

std::vector<G4double> Config::GetScintAbsLength() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintAbsLength;
}

void Config::SetScintAbsLength(const std::vector<G4double>& values) {
  if (values.empty()) {
    return;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  fScintAbsLength = values;
  ++fScintMaterialVersion;
}

std::vector<G4double> Config::GetScintSpectrum() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintSpectrum;
}

void Config::SetScintSpectrum(const std::vector<G4double>& values) {
  if (values.empty()) {
    return;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  fScintSpectrum = values;
  ++fScintMaterialVersion;
}

G4double Config::GetScintYield() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintYield;
}

void Config::SetScintYield(G4double value) {
  if (value <= 0.0) {
    return;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  fScintYield = value;
  ++fScintMaterialVersion;
}

G4double Config::GetScintResolutionScale() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintResolutionScale;
}

void Config::SetScintResolutionScale(G4double value) {
  if (value <= 0.0) {
    return;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  fScintResolutionScale = value;
  ++fScintMaterialVersion;
}

G4double Config::GetScintTimeConstant(G4int componentIndex) const {
  if (!IsValidScintillationComponentIndex(componentIndex)) {
    return 0.0;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintTimeConstants[ToZeroBasedComponentIndex(componentIndex)];
}

void Config::SetScintTimeConstant(G4int componentIndex, G4double value) {
  if (!IsValidScintillationComponentIndex(componentIndex) || value < 0.0) {
    return;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  fScintTimeConstants[ToZeroBasedComponentIndex(componentIndex)] = value;
  ++fScintMaterialVersion;
}

G4double Config::GetScintYieldFraction(G4int componentIndex) const {
  if (!IsValidScintillationComponentIndex(componentIndex)) {
    return 0.0;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintYieldFractions[ToZeroBasedComponentIndex(componentIndex)];
}

void Config::SetScintYieldFraction(G4int componentIndex, G4double value) {
  if (!IsValidScintillationComponentIndex(componentIndex) || value < 0.0) {
    return;
  }
  std::lock_guard<std::mutex> lock(fMutex);
  fScintYieldFractions[ToZeroBasedComponentIndex(componentIndex)] = value;
  ++fScintMaterialVersion;
}

G4double Config::GetScintTimeConstant() const { return GetScintTimeConstant(1); }

void Config::SetScintTimeConstant(G4double value) {
  if (value <= 0.0) {
    return;
  }
  SetScintTimeConstant(1, value);
}

G4double Config::GetScintYield1() const { return GetScintYieldFraction(1); }

void Config::SetScintYield1(G4double value) {
  if (value < 0.0) {
    return;
  }
  SetScintYieldFraction(1, value);
}

G4int Config::GetScintMaterialVersion() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fScintMaterialVersion;
}

std::string Config::GetOutputFilename() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fOutputFilename;
}

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

std::string Config::GetOutputPath() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fOutputPath;
}

void Config::SetOutputPath(const std::string& value) {
  std::string normalized = Utils::Unquote(Utils::Trim(value));
  if (!normalized.empty()) {
    normalized = std::filesystem::path(normalized).lexically_normal().string();
  }

  std::lock_guard<std::mutex> lock(fMutex);
  fOutputPath = normalized;
}

std::string Config::GetOutputRunName() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return fOutputRunName;
}

void Config::SetOutputRunName(const std::string& value) {
  std::lock_guard<std::mutex> lock(fMutex);
  fOutputRunName = SimIO::NormalizeRunName(value);
}

std::string Config::GetHdf5FilePath() const {
  std::lock_guard<std::mutex> lock(fMutex);
  return SimIO::ComposeOutputPath(fOutputFilename, fOutputPath, fOutputRunName,
                                  ".h5");
}
