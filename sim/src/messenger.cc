#include "messenger.hh"

#include "config.hh"

#include "G4ApplicationState.hh"
#include "G4RunManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4UIcmdWithADoubleAndUnit.hh"
#include "G4UIcmdWithAString.hh"
#include "G4UIdirectory.hh"
#include "G4ios.hh"

/**
 * Geant4 UI messenger responsible for runtime configuration commands.
 *
 * Responsibilities:
 * - Register `/scintillator/geom/...`, `/optical_interface/geom/...`, and `/output/...`
 *   command hierarchy.
 * - Parse user-provided command values.
 * - Forward validated values into the shared Config object.
 * - Notify the run manager when geometry-affecting fields are modified.
 */
Messenger::Messenger(Config* config) : fConfig(config) {
  // Top-level namespace for scintillator configuration commands.
  fScintillatorDir = new G4UIdirectory("/scintillator/");
  fScintillatorDir->SetGuidance("Scintillator controls");

  // Scintillator geometry/material subtree.
  fScintillatorGeomDir = new G4UIdirectory("/scintillator/geom/");
  fScintillatorGeomDir->SetGuidance("Scintillator geometry and material controls");

  // Top-level namespace for optical-interface geometry commands.
  fOpticalInterfaceDir = new G4UIdirectory("/optical_interface/");
  fOpticalInterfaceDir->SetGuidance("Optical-interface controls");

  // Optical-interface geometry subtree.
  fOpticalInterfaceGeomDir = new G4UIdirectory("/optical_interface/geom/");
  fOpticalInterfaceGeomDir->SetGuidance("Optical-interface geometry controls");

  // Output subtree (format and file destination controls).
  fOutputDir = new G4UIdirectory("/output/");
  fOutputDir->SetGuidance("Output controls");

  // Material name command; accepts NIST names or custom labels handled later.
  fGeomMaterialCmd = new G4UIcmdWithAString("/scintillator/geom/material", this);
  fGeomMaterialCmd->SetGuidance("Set scintillator material name (EJ200 or NIST name)");
  fGeomMaterialCmd->SetParameterName("material", false);
  fGeomMaterialCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Scintillator X dimension command in Geant4 length units.
  fGeomScintXCmd = new G4UIcmdWithADoubleAndUnit("/scintillator/geom/scintX", this);
  fGeomScintXCmd->SetGuidance("Set scintillator size in X");
  fGeomScintXCmd->SetParameterName("scintX", false);
  fGeomScintXCmd->SetUnitCategory("Length");
  fGeomScintXCmd->SetRange("scintX > 0.");
  fGeomScintXCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Scintillator Y dimension command.
  fGeomScintYCmd = new G4UIcmdWithADoubleAndUnit("/scintillator/geom/scintY", this);
  fGeomScintYCmd->SetGuidance("Set scintillator size in Y");
  fGeomScintYCmd->SetParameterName("scintY", false);
  fGeomScintYCmd->SetUnitCategory("Length");
  fGeomScintYCmd->SetRange("scintY > 0.");
  fGeomScintYCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Scintillator thickness (Z) command.
  fGeomScintZCmd = new G4UIcmdWithADoubleAndUnit("/scintillator/geom/scintZ", this);
  fGeomScintZCmd->SetGuidance("Set scintillator thickness in Z");
  fGeomScintZCmd->SetParameterName("scintZ", false);
  fGeomScintZCmd->SetUnitCategory("Length");
  fGeomScintZCmd->SetRange("scintZ > 0.");
  fGeomScintZCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Scintillator absolute center-position commands in world coordinates.
  fGeomScintPosXCmd = new G4UIcmdWithADoubleAndUnit("/scintillator/geom/posX", this);
  fGeomScintPosXCmd->SetGuidance("Set scintillator center X position in world coordinates");
  fGeomScintPosXCmd->SetParameterName("posX", false);
  fGeomScintPosXCmd->SetUnitCategory("Length");
  fGeomScintPosXCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  fGeomScintPosYCmd = new G4UIcmdWithADoubleAndUnit("/scintillator/geom/posY", this);
  fGeomScintPosYCmd->SetGuidance("Set scintillator center Y position in world coordinates");
  fGeomScintPosYCmd->SetParameterName("posY", false);
  fGeomScintPosYCmd->SetUnitCategory("Length");
  fGeomScintPosYCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  fGeomScintPosZCmd = new G4UIcmdWithADoubleAndUnit("/scintillator/geom/posZ", this);
  fGeomScintPosZCmd->SetGuidance("Set scintillator center Z position in world coordinates");
  fGeomScintPosZCmd->SetParameterName("posZ", false);
  fGeomScintPosZCmd->SetUnitCategory("Length");
  fGeomScintPosZCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Aperture radius command for circular pass-through region at scintillator +Z face.
  fGeomApertureRadiusCmd =
      new G4UIcmdWithADoubleAndUnit("/scintillator/geom/apertureRadius", this);
  fGeomApertureRadiusCmd->SetGuidance(
      "Set circular aperture radius on scintillator +Z face (0 disables aperture)");
  fGeomApertureRadiusCmd->SetParameterName("apertureRadius", false);
  fGeomApertureRadiusCmd->SetUnitCategory("Length");
  fGeomApertureRadiusCmd->SetRange("apertureRadius >= 0.");
  fGeomApertureRadiusCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Optical-interface dimensions (X, Y) and thickness (Z).
  fOpticalInterfaceXCmd =
      new G4UIcmdWithADoubleAndUnit("/optical_interface/geom/sizeX", this);
  fOpticalInterfaceXCmd->SetGuidance(
      "Set optical-interface size in X (0 means inherit scintillator X)");
  fOpticalInterfaceXCmd->SetParameterName("sizeX", false);
  fOpticalInterfaceXCmd->SetUnitCategory("Length");
  fOpticalInterfaceXCmd->SetRange("sizeX >= 0.");
  fOpticalInterfaceXCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  fOpticalInterfaceYCmd =
      new G4UIcmdWithADoubleAndUnit("/optical_interface/geom/sizeY", this);
  fOpticalInterfaceYCmd->SetGuidance(
      "Set optical-interface size in Y (0 means inherit scintillator Y)");
  fOpticalInterfaceYCmd->SetParameterName("sizeY", false);
  fOpticalInterfaceYCmd->SetUnitCategory("Length");
  fOpticalInterfaceYCmd->SetRange("sizeY >= 0.");
  fOpticalInterfaceYCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  fOpticalInterfaceThicknessCmd =
      new G4UIcmdWithADoubleAndUnit("/optical_interface/geom/thickness", this);
  fOpticalInterfaceThicknessCmd->SetGuidance("Set optical-interface thickness in Z");
  fOpticalInterfaceThicknessCmd->SetParameterName("thickness", false);
  fOpticalInterfaceThicknessCmd->SetUnitCategory("Length");
  fOpticalInterfaceThicknessCmd->SetRange("thickness > 0.");
  fOpticalInterfaceThicknessCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Optical-interface center-position commands in world coordinates.
  fOpticalInterfacePosXCmd = new G4UIcmdWithADoubleAndUnit("/optical_interface/geom/posX", this);
  fOpticalInterfacePosXCmd->SetGuidance(
      "Set optical-interface center X position in world coordinates (default aligns with scintillator center)");
  fOpticalInterfacePosXCmd->SetParameterName("posX", false);
  fOpticalInterfacePosXCmd->SetUnitCategory("Length");
  fOpticalInterfacePosXCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  fOpticalInterfacePosYCmd = new G4UIcmdWithADoubleAndUnit("/optical_interface/geom/posY", this);
  fOpticalInterfacePosYCmd->SetGuidance(
      "Set optical-interface center Y position in world coordinates (default aligns with scintillator center)");
  fOpticalInterfacePosYCmd->SetParameterName("posY", false);
  fOpticalInterfacePosYCmd->SetUnitCategory("Length");
  fOpticalInterfacePosYCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  fOpticalInterfacePosZCmd = new G4UIcmdWithADoubleAndUnit("/optical_interface/geom/posZ", this);
  fOpticalInterfacePosZCmd->SetGuidance(
      "Set optical-interface center Z position in world coordinates (default is flush on scintillator +Z face when not set)");
  fOpticalInterfacePosZCmd->SetParameterName("posZ", false);
  fOpticalInterfacePosZCmd->SetUnitCategory("Length");
  fOpticalInterfacePosZCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Output format command. Allowed values are constrained by SetCandidates.
  fOutputFormatCmd = new G4UIcmdWithAString("/output/format", this);
  fOutputFormatCmd->SetGuidance("Set output format: csv, hdf5, both");
  fOutputFormatCmd->SetParameterName("format", false);
  fOutputFormatCmd->SetCandidates("csv hdf5 both");
  fOutputFormatCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Output directory command. Empty string clears explicit override.
  fOutputPathCmd = new G4UIcmdWithAString("/output/path", this);
  fOutputPathCmd->SetGuidance(
      "Set output directory path. Use \"\" to clear and fall back to legacy base-path behavior.");
  fOutputPathCmd->SetParameterName("path", false);
  fOutputPathCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Output filename command.
  fOutputFilenameCmd = new G4UIcmdWithAString("/output/filename", this);
  fOutputFilenameCmd->SetGuidance(
      "Set output base filename/path; .csv/.h5 extension is added automatically");
  fOutputFilenameCmd->SetParameterName("filename", false);
  fOutputFilenameCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Optional run-name command used for routing outputs to data/<runname>/.
  fOutputRunNameCmd = new G4UIcmdWithAString("/output/runname", this);
  fOutputRunNameCmd->SetGuidance(
      "Set optional run name; outputs go under <output/path>/<runname>/ when path is set, otherwise data/<runname>/. Use \"\" to clear.");
  fOutputRunNameCmd->SetParameterName("runname", false);
  fOutputRunNameCmd->AvailableForStates(G4State_PreInit, G4State_Idle);
}

/**
 * Destroy all UI command and directory objects owned by this messenger.
 *
 * Deletion is performed in reverse ownership order for clarity and to mirror
 * constructor allocation flow.
 */
Messenger::~Messenger() {
  delete fOutputRunNameCmd;
  delete fOutputFilenameCmd;
  delete fOutputPathCmd;
  delete fOutputFormatCmd;

  delete fOpticalInterfacePosZCmd;
  delete fOpticalInterfacePosYCmd;
  delete fOpticalInterfacePosXCmd;

  delete fOpticalInterfaceThicknessCmd;
  delete fOpticalInterfaceYCmd;
  delete fOpticalInterfaceXCmd;

  delete fGeomScintPosZCmd;
  delete fGeomScintPosYCmd;
  delete fGeomScintPosXCmd;
  delete fGeomApertureRadiusCmd;
  delete fGeomScintZCmd;
  delete fGeomScintYCmd;
  delete fGeomScintXCmd;
  delete fGeomMaterialCmd;

  delete fOutputDir;
  delete fOpticalInterfaceGeomDir;
  delete fOpticalInterfaceDir;
  delete fScintillatorGeomDir;
  delete fScintillatorDir;
}

/**
 * Dispatch callback invoked by Geant4 when one registered command is executed.
 *
 * This method:
 * - maps command pointer identity to a specific Config mutation,
 * - performs command-specific value conversion where needed,
 * - emits concise status feedback to stdout,
 * - marks geometry dirty after geometry-affecting command changes.
 */
void Messenger::SetNewValue(G4UIcommand* command, G4String newValue) {
  if (!fConfig) {
    return;
  }

  // Material change affects geometry/material tables used during initialization.
  if (command == fGeomMaterialCmd) {
    fConfig->SetScintMaterial(newValue);
    G4cout << "Scintillator material set to '" << newValue
           << "'. Run /run/initialize before /beamOn." << G4endl;
    NotifyGeometryChanged();
    return;
  }

  // Scintillator dimensions are parsed in configured units by Geant4 helpers.
  if (command == fGeomScintXCmd) {
    fConfig->SetScintX(fGeomScintXCmd->GetNewDoubleValue(newValue));
    NotifyGeometryChanged();
    return;
  }

  if (command == fGeomScintYCmd) {
    fConfig->SetScintY(fGeomScintYCmd->GetNewDoubleValue(newValue));
    NotifyGeometryChanged();
    return;
  }

  if (command == fGeomScintZCmd) {
    fConfig->SetScintZ(fGeomScintZCmd->GetNewDoubleValue(newValue));
    NotifyGeometryChanged();
    return;
  }

  if (command == fGeomScintPosXCmd) {
    fConfig->SetScintPosX(fGeomScintPosXCmd->GetNewDoubleValue(newValue));
    NotifyGeometryChanged();
    return;
  }

  if (command == fGeomScintPosYCmd) {
    fConfig->SetScintPosY(fGeomScintPosYCmd->GetNewDoubleValue(newValue));
    NotifyGeometryChanged();
    return;
  }

  if (command == fGeomScintPosZCmd) {
    fConfig->SetScintPosZ(fGeomScintPosZCmd->GetNewDoubleValue(newValue));
    NotifyGeometryChanged();
    return;
  }

  if (command == fGeomApertureRadiusCmd) {
    fConfig->SetApertureRadius(
        fGeomApertureRadiusCmd->GetNewDoubleValue(newValue));
    NotifyGeometryChanged();
    return;
  }

  // Optical-interface dimensions are controlled in dedicated /optical_interface/geom subtree.
  if (command == fOpticalInterfaceXCmd) {
    fConfig->SetOpticalInterfaceX(fOpticalInterfaceXCmd->GetNewDoubleValue(newValue));
    NotifyGeometryChanged();
    return;
  }

  if (command == fOpticalInterfaceYCmd) {
    fConfig->SetOpticalInterfaceY(fOpticalInterfaceYCmd->GetNewDoubleValue(newValue));
    NotifyGeometryChanged();
    return;
  }

  if (command == fOpticalInterfaceThicknessCmd) {
    fConfig->SetOpticalInterfaceThickness(fOpticalInterfaceThicknessCmd->GetNewDoubleValue(newValue));
    NotifyGeometryChanged();
    return;
  }

  // Optical-interface absolute center position controls.
  if (command == fOpticalInterfacePosXCmd) {
    const auto value = fOpticalInterfacePosXCmd->GetNewDoubleValue(newValue);
    fConfig->SetOpticalInterfacePosX(value);
    G4cout << "Optical-interface posX set to " << value / mm << " mm." << G4endl;
    NotifyGeometryChanged();
    return;
  }

  if (command == fOpticalInterfacePosYCmd) {
    const auto value = fOpticalInterfacePosYCmd->GetNewDoubleValue(newValue);
    fConfig->SetOpticalInterfacePosY(value);
    G4cout << "Optical-interface posY set to " << value / mm << " mm." << G4endl;
    NotifyGeometryChanged();
    return;
  }

  if (command == fOpticalInterfacePosZCmd) {
    const auto value = fOpticalInterfacePosZCmd->GetNewDoubleValue(newValue);
    fConfig->SetOpticalInterfacePosZ(value);
    G4cout << "Optical-interface posZ set to " << value / mm << " mm." << G4endl;
    NotifyGeometryChanged();
    return;
  }

  // Output format selection controls which writer(s) EventAction invokes.
  if (command == fOutputFormatCmd) {
    if (!fConfig->SetOutputFormat(newValue)) {
      G4cout << "Unknown format '" << newValue
             << "'. Allowed values: csv, hdf5, both" << G4endl;
      return;
    }
    G4cout << "Output format set to '"
           << Config::OutputFormatToString(fConfig->GetOutputFormat()) << "'."
           << G4endl;
    return;
  }

  // Output-path override controls destination directory for output writers.
  if (command == fOutputPathCmd) {
    fConfig->SetOutputPath(newValue);
    const auto configuredPath = fConfig->GetOutputPath();
    if (configuredPath.empty()) {
      G4cout << "Output path cleared (using legacy filename-path behavior)."
             << G4endl;
    } else {
      G4cout << "Output path set to '" << configuredPath << "'." << G4endl;
    }

    const auto mode = fConfig->GetOutputFormat();
    if (mode == Config::OutputFormat::kCsv) {
      G4cout << "CSV path: '" << fConfig->GetCsvFilePath() << "'." << G4endl;
    } else if (mode == Config::OutputFormat::kHdf5) {
      G4cout << "HDF5 path: '" << fConfig->GetHdf5FilePath() << "'." << G4endl;
    } else {
      G4cout << "CSV path: '" << fConfig->GetCsvFilePath()
             << "', HDF5 path: '" << fConfig->GetHdf5FilePath() << "'."
             << G4endl;
    }
    return;
  }

  // Output filename is format-agnostic; extension is derived automatically.
  if (command == fOutputFilenameCmd) {
    fConfig->SetOutputFilename(newValue);
    const auto mode = fConfig->GetOutputFormat();
    if (mode == Config::OutputFormat::kCsv) {
      G4cout << "Output filename set. CSV path: '" << fConfig->GetCsvFilePath()
             << "'." << G4endl;
    } else if (mode == Config::OutputFormat::kHdf5) {
      G4cout << "Output filename set. HDF5 path: '" << fConfig->GetHdf5FilePath()
             << "'." << G4endl;
    } else {
      G4cout << "Output filename set. CSV path: '" << fConfig->GetCsvFilePath()
             << "', HDF5 path: '" << fConfig->GetHdf5FilePath() << "'."
             << G4endl;
    }
    return;
  }

  // Run name controls optional output routing under run-specific output folders.
  if (command == fOutputRunNameCmd) {
    fConfig->SetOutputRunName(newValue);
    const auto runName = fConfig->GetOutputRunName();
    if (runName.empty()) {
      G4cout << "Output run name cleared." << G4endl;
    } else {
      G4cout << "Output run name set to '" << runName << "'." << G4endl;
    }

    const auto mode = fConfig->GetOutputFormat();
    if (mode == Config::OutputFormat::kCsv) {
      G4cout << "CSV path: '" << fConfig->GetCsvFilePath() << "'." << G4endl;
    } else if (mode == Config::OutputFormat::kHdf5) {
      G4cout << "HDF5 path: '" << fConfig->GetHdf5FilePath() << "'." << G4endl;
    } else {
      G4cout << "CSV path: '" << fConfig->GetCsvFilePath()
             << "', HDF5 path: '" << fConfig->GetHdf5FilePath() << "'."
             << G4endl;
    }
    return;
  }
}

/**
 * Notify Geant4 that geometry-dependent data should be rebuilt before running.
 *
 * This is required after runtime geometry parameter changes to ensure the next
 * `/run/initialize` uses updated detector dimensions/material choices.
 */
void Messenger::NotifyGeometryChanged() const {
  auto* runManager = G4RunManager::GetRunManager();
  if (runManager) {
    // Mark detector geometry as dirty. We intentionally avoid forcing an
    // immediate destructive rebuild from this callback because active
    // visualization scenes can still reference old physical-volume models.
    // A forced rebuild in that state can trigger model invalidation warnings
    // and, on some Geant4/OGL stacks, a segmentation fault.
    runManager->GeometryHasBeenModified();
  }
  G4cout << "Geometry updated. Run /run/reinitializeGeometry, then /run/initialize, then /vis/drawVolume."
         << G4endl;
}
