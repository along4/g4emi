#include "DetectorConstruction.hh"
#include "PhotonSensorSD.hh"
#include "config.hh"

#include "G4Box.hh"
#include "G4Colour.hh"
#include "G4Element.hh"
#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4MaterialPropertiesTable.hh"
#include "G4NistManager.hh"
#include "G4PVPlacement.hh"
#include "G4SDManager.hh"
#include "G4SubtractionSolid.hh"
#include "G4SystemOfUnits.hh"
#include "G4ThreeVector.hh"
#include "G4Tubs.hh"
#include "G4VisAttributes.hh"
#include "G4ios.hh"

#include <algorithm>
#include <cmath>
#include <limits>
#include <string>

namespace {
/**
 * Number of tabulation points used for optical material properties.
 *
 * The same energy grid is reused for scintillator and world (air) optical
 * properties so Geant4 interpolation remains consistent across boundaries.
 */
constexpr G4int kNEntries = 5;

/**
 * Guard against invalid configuration values.
 *
 * Messenger/UI commands already enforce positive ranges, but this defensive
 * check ensures geometry construction still succeeds if values are injected
 * programmatically or if validation changes later.
 */
G4double PositiveOrDefault(G4double value, G4double fallback) {
  return (value > 0.0) ? value : fallback;
}

/**
 * Build (once) and return the custom EJ200 material used by this application.
 *
 * Design notes:
 * - We use a custom material rather than a NIST alias to control scintillation
 *   and optical transport parameters explicitly.
 * - The function first checks the Geant4 material table so repeated
 *   geometry reinitialization does not duplicate EJ200 definitions.
 *
 * Data provenance for EJ200 constants used below:
 * - Primary source: Eljen EJ-200/EJ-204/EJ-208/EJ-212 product page and data sheet.
 *   URL: https://eljentechnology.com/products
 * - Values taken directly from Eljen tables:
 *   density = 1.023 g/cm^3, refractive index = 1.58,
 *   attenuation length = 380 cm, decay time = 2.1 ns,
 *   scintillation efficiency = 10,000 photons / MeV.
 * - Emission-shape weights (scintSpectrum) are an approximate discretization
 *   of the EJ-200 emission-spectrum plot, not a digitized vendor table.
 *   They should be treated as a practical placeholder shape for transport studies.
 */
G4Material* BuildOrGetEJ200(G4NistManager* nist) {
  if (auto* existing = G4Material::GetMaterial("EJ200", false)) {
    return existing;
  }

  auto* carbon = nist->FindOrBuildElement("C");
  auto* hydrogen = nist->FindOrBuildElement("H");

  auto* scintMaterial = new G4Material("EJ200", 1.023 * g / cm3, 2);
  scintMaterial->AddElement(carbon, 9);
  scintMaterial->AddElement(hydrogen, 10);

  // Energy nodes spanning the visible/near-UV region around EJ-200 emission.
  // Chosen as a compact grid for interpolation (not a vendor tabulation).
  G4double photonEnergy[kNEntries] = {2.00 * eV, 2.40 * eV, 2.76 * eV, 3.10 * eV,
                                      3.50 * eV};
  // Vendor value: refractive index n = 1.58 (treated as approximately flat here).
  G4double rIndex[kNEntries] = {1.58, 1.58, 1.58, 1.58, 1.58};
  // Vendor value: light attenuation length = 380 cm.
  // We taper at higher energies to emulate stronger short-wavelength loss.
  G4double absLength[kNEntries] = {380.0 * cm, 380.0 * cm, 380.0 * cm, 300.0 * cm,
                                   220.0 * cm};
  // Approximate relative emission profile from EJ-200 spectrum figure.
  // Normalize shape with SCINTILLATIONYIELD below (absolute photon yield).
  G4double scintSpectrum[kNEntries] = {0.05, 0.35, 1.00, 0.45, 0.08};

  auto* mpt = new G4MaterialPropertiesTable();
  mpt->AddProperty("RINDEX", photonEnergy, rIndex, kNEntries);
  mpt->AddProperty("ABSLENGTH", photonEnergy, absLength, kNEntries);
  mpt->AddProperty("SCINTILLATIONCOMPONENT1", photonEnergy, scintSpectrum, kNEntries);
  // Vendor scintillation efficiency: ~10,000 photons / MeV for EJ-200.
  mpt->AddConstProperty("SCINTILLATIONYIELD", 10000.0 / MeV);
  mpt->AddConstProperty("RESOLUTIONSCALE", 1.0);
  // Vendor decay time: 2.1 ns (single-component model used here).
  mpt->AddConstProperty("SCINTILLATIONTIMECONSTANT1", 2.1 * ns);
  mpt->AddConstProperty("SCINTILLATIONYIELD1", 1.0);
  scintMaterial->SetMaterialPropertiesTable(mpt);

  return scintMaterial;
}

/**
 * Build (once) and return a highly absorbing optical material for aperture masks.
 */
G4Material* BuildOrGetApertureAbsorber(G4NistManager* nist) {
  if (auto* existing = G4Material::GetMaterial("ApertureAbsorber", false)) {
    return existing;
  }

  auto* carbon = nist->FindOrBuildElement("C");
  auto* absorber = new G4Material("ApertureAbsorber", 2.0 * g / cm3, 1);
  absorber->AddElement(carbon, 1);

  G4double photonEnergy[kNEntries] = {2.00 * eV, 2.40 * eV, 2.76 * eV, 3.10 * eV,
                                      3.50 * eV};
  G4double rIndex[kNEntries] = {1.5, 1.5, 1.5, 1.5, 1.5};
  G4double absLength[kNEntries] = {1.0 * um, 1.0 * um, 1.0 * um, 1.0 * um,
                                   1.0 * um};

  auto* mpt = new G4MaterialPropertiesTable();
  mpt->AddProperty("RINDEX", photonEnergy, rIndex, kNEntries);
  mpt->AddProperty("ABSLENGTH", photonEnergy, absLength, kNEntries);
  absorber->SetMaterialPropertiesTable(mpt);

  return absorber;
}
}  // namespace

/**
 * Detector construction is parameterized by Config so macro/UI commands can
 * modify geometry and material choices prior to /run/initialize.
 */
DetectorConstruction::DetectorConstruction(const Config* config) : fConfig(config) {}

/**
 * Build geometry and materials for one run-manager initialization.
 *
 * Geometry layout:
 * - World: air box, auto-sized to stay comfortably larger than active volumes.
 * - Scintillator: centered EJ200 (or requested material) slab with configurable
 *   size and world position.
 * - Sensor: thin plane (size/position configurable) used to record optical hits.
 *
 * Optical transport:
 * - World air gets RINDEX/ABSLENGTH to avoid undefined optical boundaries.
 * - Scintillator gets scintillation and attenuation properties through EJ200 MPT.
 */
G4VPhysicalVolume* DetectorConstruction::Construct() {
  auto* nist = G4NistManager::Instance();
  auto* worldMaterial = nist->FindOrBuildMaterial("G4_AIR");

  // Resolve scintillator material from config; unknown names fall back to EJ200.
  G4Material* scintMaterial = nullptr;
  std::string scintMaterialName = "EJ200";
  if (fConfig) {
    scintMaterialName = fConfig->GetScintMaterial();
  }

  if (scintMaterialName == "EJ200") {
    scintMaterial = BuildOrGetEJ200(nist);
  } else {
    scintMaterial = nist->FindOrBuildMaterial(scintMaterialName, false);
    if (!scintMaterial) {
      G4cout << "Material '" << scintMaterialName
             << "' not found. Falling back to EJ200." << G4endl;
      scintMaterial = BuildOrGetEJ200(nist);
    }
  }

  // Give world material optical properties so optical photons can propagate
  // with a well-defined refractive index and absorption length in air.
  auto* worldMpt = new G4MaterialPropertiesTable();
  G4double photonEnergy[kNEntries] = {2.00 * eV, 2.40 * eV, 2.76 * eV, 3.10 * eV,
                                      3.50 * eV};
  G4double airRindex[kNEntries] = {1.0, 1.0, 1.0, 1.0, 1.0};
  G4double airAbsLength[kNEntries] = {1000.0 * m, 1000.0 * m, 1000.0 * m, 1000.0 * m,
                                      1000.0 * m};
  worldMpt->AddProperty("RINDEX", photonEnergy, airRindex, kNEntries);
  worldMpt->AddProperty("ABSLENGTH", photonEnergy, airAbsLength, kNEntries);
  worldMaterial->SetMaterialPropertiesTable(worldMpt);

  // Geometry defaults match the baseline setup and may be overridden by
  // /scintillator/geom/* and /sensor/geom/* commands before /run/initialize.
  auto scintX = 5.0 * cm;
  auto scintY = 5.0 * cm;
  auto scintZ = 1.0 * cm;

  // Scintillator defaults to world origin.
  auto scintPosX = 0.0 * mm;
  auto scintPosY = 0.0 * mm;
  auto scintPosZ = 0.0 * mm;

  // Sensor defaults to covering the scintillator back face unless overridden.
  auto sensorX = scintX;
  auto sensorY = scintY;
  auto sensorThickness = 0.1 * mm;

  // Sensor default center: aligned with scintillator X/Y and flush on +Z face.
  auto sensorPosX = std::numeric_limits<G4double>::quiet_NaN();
  auto sensorPosY = std::numeric_limits<G4double>::quiet_NaN();
  auto sensorPosZ = std::numeric_limits<G4double>::quiet_NaN();

  // Optional circular aperture pass-through radius at scintillator +Z face.
  auto apertureRadius = 0.0 * mm;
  const auto apertureThickness = 0.01 * mm;

  if (fConfig) {
    scintX = PositiveOrDefault(fConfig->GetScintX(), scintX);
    scintY = PositiveOrDefault(fConfig->GetScintY(), scintY);
    scintZ = PositiveOrDefault(fConfig->GetScintZ(), scintZ);

    scintPosX = fConfig->GetScintPosX();
    scintPosY = fConfig->GetScintPosY();
    scintPosZ = fConfig->GetScintPosZ();

    sensorX = PositiveOrDefault(fConfig->GetSensorX(), scintX);
    sensorY = PositiveOrDefault(fConfig->GetSensorY(), scintY);
    sensorThickness =
        PositiveOrDefault(fConfig->GetSensorThickness(), sensorThickness);

    sensorPosX = fConfig->GetSensorPosX();
    sensorPosY = fConfig->GetSensorPosY();
    sensorPosZ = fConfig->GetSensorPosZ();
    apertureRadius = std::max(0.0, fConfig->GetApertureRadius());
  }

  const auto scintBackFaceZ = scintPosZ + 0.5 * scintZ;
  const auto apertureCenterZ = scintBackFaceZ + 0.5 * apertureThickness;
  const auto apertureMaxRadius = std::hypot(0.5 * scintX, 0.5 * scintY);
  auto apertureEnabled = apertureRadius > 0.0;

  if (apertureEnabled && apertureRadius >= apertureMaxRadius) {
    G4cout << "[Geom] apertureRadius (" << apertureRadius / mm
           << " mm) is larger than the scintillator half-diagonal ("
           << apertureMaxRadius / mm << " mm). Aperture mask disabled."
           << G4endl;
    apertureEnabled = false;
  }

  const auto defaultSensorX = scintPosX;
  const auto defaultSensorY = scintPosY;
  const auto defaultSensorZ =
      scintBackFaceZ + (apertureEnabled ? apertureThickness : 0.0) +
      0.5 * sensorThickness;

  const auto sensorCenterX = std::isnan(sensorPosX) ? defaultSensorX : sensorPosX;
  const auto sensorCenterY = std::isnan(sensorPosY) ? defaultSensorY : sensorPosY;
  const auto sensorCenterZ = std::isnan(sensorPosZ) ? defaultSensorZ : sensorPosZ;

  G4cout << "[Geom] Scint(mm)=(" << scintPosX / mm << "," << scintPosY / mm
         << "," << scintPosZ / mm << ") Sensor(mm)=(" << sensorCenterX / mm
         << "," << sensorCenterY / mm << "," << sensorCenterZ / mm
         << ") ApertureR(mm)=" << apertureRadius / mm << G4endl;

  // Keep world automatically large enough even when volumes are shifted.
  // We size from required half-extents with a 4x safety factor.
  const auto requiredHalfX = std::max(std::abs(scintPosX) + 0.5 * scintX,
                                      std::abs(sensorCenterX) + 0.5 * sensorX);
  const auto requiredHalfY = std::max(std::abs(scintPosY) + 0.5 * scintY,
                                      std::abs(sensorCenterY) + 0.5 * sensorY);
  auto requiredHalfZ = std::max(std::abs(scintPosZ) + 0.5 * scintZ,
                                std::abs(sensorCenterZ) + 0.5 * sensorThickness);
  if (apertureEnabled) {
    requiredHalfZ =
        std::max(requiredHalfZ, std::abs(apertureCenterZ) + 0.5 * apertureThickness);
  }

  const auto worldX = std::max(1.0 * m, 8.0 * requiredHalfX);
  const auto worldY = std::max(1.0 * m, 8.0 * requiredHalfY);
  const auto worldZ = std::max(1.0 * m, 8.0 * requiredHalfZ);

  auto* worldSolid = new G4Box("WorldSolid", 0.5 * worldX, 0.5 * worldY, 0.5 * worldZ);
  auto* worldLV = new G4LogicalVolume(worldSolid, worldMaterial, "WorldLV");
  auto* worldPV =
      new G4PVPlacement(nullptr, {}, worldLV, "WorldPV", nullptr, false, 0, true);

  auto* scintSolid =
      new G4Box("ScintillatorSolid", 0.5 * scintX, 0.5 * scintY, 0.5 * scintZ);
  fScoringVolume =
      new G4LogicalVolume(scintSolid, scintMaterial, "ScintillatorLV");

  new G4PVPlacement(nullptr,
                    G4ThreeVector(scintPosX, scintPosY, scintPosZ),
                    fScoringVolume,
                    "ScintillatorPV",
                    worldLV,
                    false,
                    0,
                    true);

  // Visualization: tint scintillator so sensor motion is easier to see.
  static auto* scintVisAttributes = []() {
    auto* vis = new G4VisAttributes(G4Colour(0.1, 0.5, 0.9, 0.35));
    vis->SetVisibility(true);
    vis->SetForceSolid(true);
    return vis;
  }();
  fScoringVolume->SetVisAttributes(scintVisAttributes);

  if (apertureEnabled) {
    constexpr auto kApertureClearance = 1.0 * um;
    const auto maskHalfX = std::max(0.0 * mm, 0.5 * scintX - kApertureClearance);
    const auto maskHalfY = std::max(0.0 * mm, 0.5 * scintY - kApertureClearance);

    if (maskHalfX > 0.0 && maskHalfY > 0.0) {
      auto* apertureOuter = new G4Box("ScintApertureOuterSolid", maskHalfX, maskHalfY,
                                      0.5 * apertureThickness);
      auto* apertureHole =
          new G4Tubs("ScintApertureHoleSolid", 0.0, apertureRadius,
                     0.5 * apertureThickness + kApertureClearance, 0.0, 360.0 * deg);
      auto* apertureSolid =
          new G4SubtractionSolid("ScintApertureSolid", apertureOuter, apertureHole);
      auto* apertureLV = new G4LogicalVolume(
          apertureSolid, BuildOrGetApertureAbsorber(nist), "ScintApertureLV");

      static auto* apertureVisAttributes = []() {
        auto* vis = new G4VisAttributes(G4Colour(0.0, 0.2, 1.0, 0.9));
        vis->SetVisibility(true);
        vis->SetForceSolid(true);
        return vis;
      }();
      apertureLV->SetVisAttributes(apertureVisAttributes);

      new G4PVPlacement(nullptr,
                        G4ThreeVector(scintPosX, scintPosY, apertureCenterZ),
                        apertureLV,
                        "ScintAperturePV",
                        worldLV,
                        false,
                        0,
                        true);
    }
  }

  // Photon sensor is a dedicated logical volume used only for hit collection.
  auto* sensorSolid = new G4Box("PhotonSensorSolid", 0.5 * sensorX, 0.5 * sensorY,
                                0.5 * sensorThickness);
  fPhotonSensorVolume =
      new G4LogicalVolume(sensorSolid, worldMaterial, "PhotonSensorLV");

  // Visualization: draw the sensor in solid red so it is easy to identify in OGL.
  static auto* sensorVisAttributes = []() {
    auto* vis = new G4VisAttributes(G4Colour(1.0, 0.0, 0.0));
    vis->SetVisibility(true);
    vis->SetForceSolid(true);
    return vis;
  }();
  fPhotonSensorVolume->SetVisAttributes(sensorVisAttributes);

  new G4PVPlacement(nullptr,
                    G4ThreeVector(sensorCenterX, sensorCenterY, sensorCenterZ),
                    fPhotonSensorVolume,
                    "PhotonSensorPV",
                    worldLV,
                    false,
                    0,
                    true);

  return worldPV;
}

/**
 * Attach sensitive detector(s) after geometry is built.
 *
 * We register a single PhotonSensorSD instance and assign it to the sensor
 * logical volume. If geometry was not built (or failed), we skip safely.
 */
void DetectorConstruction::ConstructSDandField() {
  if (!fPhotonSensorVolume) {
    return;
  }

  auto* sdManager = G4SDManager::GetSDMpointer();

  // Reuse the existing SD across geometry reinitializations. This avoids
  // duplicate-registration warnings (DET1010) when geometry commands trigger
  // /run/reinitializeGeometry in interactive sessions.
  auto* existing = sdManager->FindSensitiveDetector("PhotonSensorSD", false);
  auto* photonSensor = existing ? static_cast<PhotonSensorSD*>(existing)
                                : new PhotonSensorSD("PhotonSensorSD");

  if (!existing) {
    sdManager->AddNewDetector(photonSensor);
  }

  SetSensitiveDetector(fPhotonSensorVolume, photonSensor);
}
