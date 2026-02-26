#include "DetectorConstruction.hh"
#include "PhotonOpticalInterfaceSD.hh"
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
#include <vector>

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

struct ScintillatorMaterialConfig {
  std::string baseName = "EJ200";
  G4double density = 1.023 * g / cm3;
  G4int carbonAtoms = 9;
  G4int hydrogenAtoms = 10;
  std::vector<G4double> photonEnergy = {
      2.00 * eV, 2.40 * eV, 2.76 * eV, 3.10 * eV, 3.50 * eV};
  std::vector<G4double> rIndex = {1.58, 1.58, 1.58, 1.58, 1.58};
  std::vector<G4double> absLength = {
      380.0 * cm, 380.0 * cm, 380.0 * cm, 300.0 * cm, 220.0 * cm};
  std::vector<G4double> scintSpectrum = {0.05, 0.35, 1.00, 0.45, 0.08};
  G4double scintYieldPerMeV = 10000.0;
  G4double resolutionScale = 1.0;
  G4double timeConstant = 2.1 * ns;
  G4double yield1 = 1.0;
  G4int version = 0;
};

ScintillatorMaterialConfig ResolveScintillatorMaterialConfig(const Config* config) {
  ScintillatorMaterialConfig out;
  if (!config) {
    return out;
  }

  out.density = config->GetScintDensity();
  out.carbonAtoms = config->GetScintCarbonAtoms();
  out.hydrogenAtoms = config->GetScintHydrogenAtoms();
  out.photonEnergy = config->GetScintPhotonEnergy();
  out.rIndex = config->GetScintRIndex();
  out.absLength = config->GetScintAbsLength();
  out.scintSpectrum = config->GetScintSpectrum();
  out.scintYieldPerMeV = config->GetScintYield();
  out.resolutionScale = config->GetScintResolutionScale();
  out.timeConstant = config->GetScintTimeConstant();
  out.yield1 = config->GetScintYield1();
  out.version = config->GetScintMaterialVersion();

  if (out.density <= 0.0) {
    out.density = 1.023 * g / cm3;
  }
  if (out.carbonAtoms <= 0) {
    out.carbonAtoms = 9;
  }
  if (out.hydrogenAtoms <= 0) {
    out.hydrogenAtoms = 10;
  }
  if (out.scintYieldPerMeV <= 0.0) {
    out.scintYieldPerMeV = 10000.0;
  }
  if (out.resolutionScale <= 0.0) {
    out.resolutionScale = 1.0;
  }
  if (out.timeConstant <= 0.0) {
    out.timeConstant = 2.1 * ns;
  }
  if (out.yield1 < 0.0) {
    out.yield1 = 1.0;
  }

  const std::size_t nEntries = out.photonEnergy.size();
  if (nEntries == 0 || out.rIndex.size() != nEntries || out.absLength.size() != nEntries ||
      out.scintSpectrum.size() != nEntries) {
    G4cout << "[Scintillator] Invalid material-table sizes; falling back to EJ200 defaults."
           << G4endl;
    out.photonEnergy = {2.00 * eV, 2.40 * eV, 2.76 * eV, 3.10 * eV, 3.50 * eV};
    out.rIndex = {1.58, 1.58, 1.58, 1.58, 1.58};
    out.absLength = {380.0 * cm, 380.0 * cm, 380.0 * cm, 300.0 * cm, 220.0 * cm};
    out.scintSpectrum = {0.05, 0.35, 1.00, 0.45, 0.08};
  }

  return out;
}

/**
 * Build (once per version) and return a configurable EJ200-like material.
 */
G4Material* BuildOrGetEJ200(G4NistManager* nist, const Config* config) {
  const auto settings = ResolveScintillatorMaterialConfig(config);
  const std::string runtimeName =
      settings.baseName + "_cfg_" + std::to_string(settings.version);

  if (auto* existing = G4Material::GetMaterial(runtimeName, false)) {
    return existing;
  }

  auto* carbon = nist->FindOrBuildElement("C");
  auto* hydrogen = nist->FindOrBuildElement("H");

  auto* scintMaterial = new G4Material(runtimeName, settings.density, 2);
  scintMaterial->AddElement(carbon, settings.carbonAtoms);
  scintMaterial->AddElement(hydrogen, settings.hydrogenAtoms);

  auto* mpt = new G4MaterialPropertiesTable();
  mpt->AddProperty("RINDEX", settings.photonEnergy, settings.rIndex);
  mpt->AddProperty("ABSLENGTH", settings.photonEnergy, settings.absLength);
  mpt->AddProperty("SCINTILLATIONCOMPONENT1", settings.photonEnergy,
                   settings.scintSpectrum);
  mpt->AddConstProperty("SCINTILLATIONYIELD", settings.scintYieldPerMeV / MeV);
  mpt->AddConstProperty("RESOLUTIONSCALE", settings.resolutionScale);
  mpt->AddConstProperty("SCINTILLATIONTIMECONSTANT1", settings.timeConstant);
  mpt->AddConstProperty("SCINTILLATIONYIELD1", settings.yield1);
  scintMaterial->SetMaterialPropertiesTable(mpt);

  return scintMaterial;
}

/**
 * Build (once) and return a highly absorbing optical material for scintillator masks.
 */
G4Material* BuildOrGetMaskAbsorber(G4NistManager* nist) {
  if (auto* existing = G4Material::GetMaterial("ScintMaskAbsorber", false)) {
    return existing;
  }

  auto* carbon = nist->FindOrBuildElement("C");
  auto* absorber = new G4Material("ScintMaskAbsorber", 2.0 * g / cm3, 1);
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
 * - Optical interface: thin plane (size/position configurable) used to record optical hits.
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
    scintMaterial = BuildOrGetEJ200(nist, fConfig);
  } else {
    scintMaterial = nist->FindOrBuildMaterial(scintMaterialName, false);
    if (!scintMaterial) {
      G4cout << "Material '" << scintMaterialName
             << "' not found. Falling back to EJ200." << G4endl;
      scintMaterial = BuildOrGetEJ200(nist, fConfig);
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
  // /scintillator/geom/* and /optical_interface/geom/* commands before /run/initialize.
  auto scintX = 5.0 * cm;
  auto scintY = 5.0 * cm;
  auto scintZ = 1.0 * cm;

  // Scintillator defaults to world origin.
  auto scintPosX = 0.0 * mm;
  auto scintPosY = 0.0 * mm;
  auto scintPosZ = 0.0 * mm;

  // Optical interface defaults to covering the scintillator back face unless overridden.
  auto opticalInterfaceX = scintX;
  auto opticalInterfaceY = scintY;
  auto opticalInterfaceThickness = 0.1 * mm;

  // Optical interface default center: aligned with scintillator X/Y and flush on +Z face.
  auto opticalInterfacePosX = std::numeric_limits<G4double>::quiet_NaN();
  auto opticalInterfacePosY = std::numeric_limits<G4double>::quiet_NaN();
  auto opticalInterfacePosZ = std::numeric_limits<G4double>::quiet_NaN();

  // Optional circular mask pass-through radius at scintillator +Z face.
  auto maskRadius = 0.0 * mm;
  const auto maskThickness = 0.01 * mm;

  if (fConfig) {
    scintX = PositiveOrDefault(fConfig->GetScintX(), scintX);
    scintY = PositiveOrDefault(fConfig->GetScintY(), scintY);
    scintZ = PositiveOrDefault(fConfig->GetScintZ(), scintZ);

    scintPosX = fConfig->GetScintPosX();
    scintPosY = fConfig->GetScintPosY();
    scintPosZ = fConfig->GetScintPosZ();

    opticalInterfaceX = PositiveOrDefault(fConfig->GetOpticalInterfaceX(), scintX);
    opticalInterfaceY = PositiveOrDefault(fConfig->GetOpticalInterfaceY(), scintY);
    opticalInterfaceThickness =
        PositiveOrDefault(fConfig->GetOpticalInterfaceThickness(), opticalInterfaceThickness);

    opticalInterfacePosX = fConfig->GetOpticalInterfacePosX();
    opticalInterfacePosY = fConfig->GetOpticalInterfacePosY();
    opticalInterfacePosZ = fConfig->GetOpticalInterfacePosZ();
    maskRadius = std::max(0.0, fConfig->GetMaskRadius());
  }

  const auto scintBackFaceZ = scintPosZ + 0.5 * scintZ;
  const auto maskCenterZ = scintBackFaceZ + 0.5 * maskThickness;
  const auto maskMaxRadius = std::hypot(0.5 * scintX, 0.5 * scintY);
  auto maskEnabled = maskRadius > 0.0;

  if (maskEnabled && maskRadius >= maskMaxRadius) {
    G4cout << "[Geom] maskRadius (" << maskRadius / mm
           << " mm) is larger than the scintillator half-diagonal ("
           << maskMaxRadius / mm << " mm). Scintillator mask disabled."
           << G4endl;
    maskEnabled = false;
  }

  const auto defaultOpticalInterfaceX = scintPosX;
  const auto defaultOpticalInterfaceY = scintPosY;
  const auto defaultOpticalInterfaceZ =
      scintBackFaceZ + (maskEnabled ? maskThickness : 0.0) +
      0.5 * opticalInterfaceThickness;

  const auto opticalInterfaceCenterX = std::isnan(opticalInterfacePosX) ? defaultOpticalInterfaceX : opticalInterfacePosX;
  const auto opticalInterfaceCenterY = std::isnan(opticalInterfacePosY) ? defaultOpticalInterfaceY : opticalInterfacePosY;
  const auto opticalInterfaceCenterZ = std::isnan(opticalInterfacePosZ) ? defaultOpticalInterfaceZ : opticalInterfacePosZ;

  G4cout << "[Geom] Scint(mm)=(" << scintPosX / mm << "," << scintPosY / mm
         << "," << scintPosZ / mm << ") OpticalInterface(mm)=(" << opticalInterfaceCenterX / mm
         << "," << opticalInterfaceCenterY / mm << "," << opticalInterfaceCenterZ / mm
         << ") MaskR(mm)=" << maskRadius / mm << G4endl;

  // Keep world automatically large enough even when volumes are shifted.
  // We size from required half-extents with a 4x safety factor.
  const auto requiredHalfX = std::max(std::abs(scintPosX) + 0.5 * scintX,
                                      std::abs(opticalInterfaceCenterX) + 0.5 * opticalInterfaceX);
  const auto requiredHalfY = std::max(std::abs(scintPosY) + 0.5 * scintY,
                                      std::abs(opticalInterfaceCenterY) + 0.5 * opticalInterfaceY);
  auto requiredHalfZ = std::max(std::abs(scintPosZ) + 0.5 * scintZ,
                                std::abs(opticalInterfaceCenterZ) + 0.5 * opticalInterfaceThickness);
  if (maskEnabled) {
    requiredHalfZ =
        std::max(requiredHalfZ, std::abs(maskCenterZ) + 0.5 * maskThickness);
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

  // Visualization: tint scintillator so optical-interface motion is easier to see.
  static auto* scintVisAttributes = []() {
    auto* vis = new G4VisAttributes(G4Colour(0.1, 0.5, 0.9, 0.35));
    vis->SetVisibility(true);
    vis->SetForceSolid(true);
    return vis;
  }();
  fScoringVolume->SetVisAttributes(scintVisAttributes);

  if (maskEnabled) {
    constexpr auto kMaskClearance = 1.0 * um;
    const auto maskHalfX = std::max(0.0 * mm, 0.5 * scintX - kMaskClearance);
    const auto maskHalfY = std::max(0.0 * mm, 0.5 * scintY - kMaskClearance);

    if (maskHalfX > 0.0 && maskHalfY > 0.0) {
      auto* maskOuter = new G4Box("ScintMaskOuterSolid", maskHalfX, maskHalfY,
                                  0.5 * maskThickness);
      auto* maskHole =
          new G4Tubs("ScintMaskHoleSolid", 0.0, maskRadius,
                     0.5 * maskThickness + kMaskClearance, 0.0, 360.0 * deg);
      auto* maskSolid =
          new G4SubtractionSolid("ScintMaskSolid", maskOuter, maskHole);
      auto* maskLV = new G4LogicalVolume(
          maskSolid, BuildOrGetMaskAbsorber(nist), "ScintMaskLV");

      static auto* maskVisAttributes = []() {
        auto* vis = new G4VisAttributes(G4Colour(0.0, 0.2, 1.0, 0.9));
        vis->SetVisibility(true);
        vis->SetForceSolid(true);
        return vis;
      }();
      maskLV->SetVisAttributes(maskVisAttributes);

      new G4PVPlacement(nullptr,
                        G4ThreeVector(scintPosX, scintPosY, maskCenterZ),
                        maskLV,
                        "ScintMaskPV",
                        worldLV,
                        false,
                        0,
                        true);
    }
  }

  // Photon optical-interface is a dedicated logical volume used only for hit collection.
  auto* opticalInterfaceSolid =
      new G4Box("PhotonOpticalInterfaceSolid", 0.5 * opticalInterfaceX,
                0.5 * opticalInterfaceY, 0.5 * opticalInterfaceThickness);
  fOpticalInterfaceVolume =
      new G4LogicalVolume(opticalInterfaceSolid, worldMaterial,
                          "PhotonOpticalInterfaceLV");

  // Visualization: draw the optical interface in solid red for easy OGL inspection.
  static auto* opticalInterfaceVisAttributes = []() {
    auto* vis = new G4VisAttributes(G4Colour(1.0, 0.0, 0.0));
    vis->SetVisibility(true);
    vis->SetForceSolid(true);
    return vis;
  }();
  fOpticalInterfaceVolume->SetVisAttributes(opticalInterfaceVisAttributes);

  new G4PVPlacement(nullptr,
                    G4ThreeVector(opticalInterfaceCenterX, opticalInterfaceCenterY, opticalInterfaceCenterZ),
                    fOpticalInterfaceVolume,
                    "PhotonOpticalInterfacePV",
                    worldLV,
                    false,
                    0,
                    true);

  return worldPV;
}

/**
 * Attach sensitive detector(s) after geometry is built.
 *
 * We register a single PhotonOpticalInterfaceSD instance and assign it to the optical-interface
 * logical volume. If geometry was not built (or failed), we skip safely.
 */
void DetectorConstruction::ConstructSDandField() {
  if (!fOpticalInterfaceVolume) {
    return;
  }

  auto* sdManager = G4SDManager::GetSDMpointer();

  // Reuse the existing SD across geometry reinitializations. This avoids
  // duplicate-registration warnings (DET1010) when geometry commands trigger
  // /run/reinitializeGeometry in interactive sessions.
  auto* existing = sdManager->FindSensitiveDetector("PhotonOpticalInterfaceSD", false);
  auto* photonOpticalInterface =
      existing ? static_cast<PhotonOpticalInterfaceSD*>(existing)
               : new PhotonOpticalInterfaceSD("PhotonOpticalInterfaceSD");

  if (!existing) {
    sdManager->AddNewDetector(photonOpticalInterface);
  }

  SetSensitiveDetector(fOpticalInterfaceVolume, photonOpticalInterface);
}
