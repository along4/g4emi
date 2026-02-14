#include "DetectorConstruction.hh"
#include "PhotonSensorSD.hh"
#include "config.hh"

#include "G4Box.hh"
#include "G4Element.hh"
#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4MaterialPropertiesTable.hh"
#include "G4NistManager.hh"
#include "G4PVPlacement.hh"
#include "G4SDManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4ThreeVector.hh"
#include "G4ios.hh"

#include <algorithm>
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
 * - Scintillator: centered EJ200 (or requested material) slab.
 * - Sensor: thin plane at +Z face of the scintillator to record optical hits.
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

  // Geometry defaults match the original baseline setup and may be overridden
  // by /scintillator/geom/* commands before /run/initialize.
  auto scintX = 5.0 * cm;
  auto scintY = 5.0 * cm;
  auto scintZ = 1.0 * cm;
  auto sensorThickness = 0.1 * mm;
  if (fConfig) {
    scintX = PositiveOrDefault(fConfig->GetScintX(), scintX);
    scintY = PositiveOrDefault(fConfig->GetScintY(), scintY);
    scintZ = PositiveOrDefault(fConfig->GetScintZ(), scintZ);
    sensorThickness =
        PositiveOrDefault(fConfig->GetSensorThickness(), sensorThickness);
  }

  // Keep world automatically large enough even when the scintillator is scaled.
  // Padding factors are simple safety margins to reduce boundary-side effects.
  const auto worldX = std::max(1.0 * m, 4.0 * scintX);
  const auto worldY = std::max(1.0 * m, 4.0 * scintY);
  const auto worldZ = std::max(1.0 * m, 8.0 * (scintZ + sensorThickness));
  auto* worldSolid = new G4Box("WorldSolid", 0.5 * worldX, 0.5 * worldY, 0.5 * worldZ);
  auto* worldLV = new G4LogicalVolume(worldSolid, worldMaterial, "WorldLV");
  auto* worldPV =
      new G4PVPlacement(nullptr, {}, worldLV, "WorldPV", nullptr, false, 0, true);

  auto* scintSolid =
      new G4Box("ScintillatorSolid", 0.5 * scintX, 0.5 * scintY, 0.5 * scintZ);
  fScoringVolume =
      new G4LogicalVolume(scintSolid, scintMaterial, "ScintillatorLV");

  new G4PVPlacement(nullptr, {}, fScoringVolume, "ScintillatorPV", worldLV, false, 0,
                    true);

  // Photon sensor is a dedicated logical volume used only for hit collection.
  // It is placed flush with the positive-Z scintillator face.
  auto* sensorSolid = new G4Box("PhotonSensorSolid", 0.5 * scintX, 0.5 * scintY,
                                0.5 * sensorThickness);
  fPhotonSensorVolume =
      new G4LogicalVolume(sensorSolid, worldMaterial, "PhotonSensorLV");

  const auto sensorZ = 0.5 * scintZ + 0.5 * sensorThickness;
  new G4PVPlacement(nullptr, G4ThreeVector(0., 0., sensorZ), fPhotonSensorVolume,
                    "PhotonSensorPV", worldLV, false, 0, true);

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
  auto* photonSensor = new PhotonSensorSD("PhotonSensorSD");
  sdManager->AddNewDetector(photonSensor);
  SetSensitiveDetector(fPhotonSensorVolume, photonSensor);
}
