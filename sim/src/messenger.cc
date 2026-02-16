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
 * - Register `/scintillator/geom/...`, `/sensor/geom/...`, and `/output/...`
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

  // Top-level namespace for sensor geometry commands.
  fSensorDir = new G4UIdirectory("/sensor/");
  fSensorDir->SetGuidance("Sensor controls");

  // Sensor geometry subtree.
  fSensorGeomDir = new G4UIdirectory("/sensor/geom/");
  fSensorGeomDir->SetGuidance("Sensor geometry controls");

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

  // Sensor dimensions (X, Y) and thickness (Z).
  fSensorXCmd = new G4UIcmdWithADoubleAndUnit("/sensor/geom/sensorX", this);
  fSensorXCmd->SetGuidance("Set sensor size in X (0 means inherit scintillator X)");
  fSensorXCmd->SetParameterName("sensorX", false);
  fSensorXCmd->SetUnitCategory("Length");
  fSensorXCmd->SetRange("sensorX >= 0.");
  fSensorXCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  fSensorYCmd = new G4UIcmdWithADoubleAndUnit("/sensor/geom/sensorY", this);
  fSensorYCmd->SetGuidance("Set sensor size in Y (0 means inherit scintillator Y)");
  fSensorYCmd->SetParameterName("sensorY", false);
  fSensorYCmd->SetUnitCategory("Length");
  fSensorYCmd->SetRange("sensorY >= 0.");
  fSensorYCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  fSensorThicknessCmd =
      new G4UIcmdWithADoubleAndUnit("/sensor/geom/sensorThickness", this);
  fSensorThicknessCmd->SetGuidance("Set sensor thickness in Z");
  fSensorThicknessCmd->SetParameterName("sensorThickness", false);
  fSensorThicknessCmd->SetUnitCategory("Length");
  fSensorThicknessCmd->SetRange("sensorThickness > 0.");
  fSensorThicknessCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Sensor center-position commands in world coordinates.
  fSensorPosXCmd = new G4UIcmdWithADoubleAndUnit("/sensor/geom/posX", this);
  fSensorPosXCmd->SetGuidance(
      "Set sensor center X position in world coordinates (default aligns with scintillator center)");
  fSensorPosXCmd->SetParameterName("posX", false);
  fSensorPosXCmd->SetUnitCategory("Length");
  fSensorPosXCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  fSensorPosYCmd = new G4UIcmdWithADoubleAndUnit("/sensor/geom/posY", this);
  fSensorPosYCmd->SetGuidance(
      "Set sensor center Y position in world coordinates (default aligns with scintillator center)");
  fSensorPosYCmd->SetParameterName("posY", false);
  fSensorPosYCmd->SetUnitCategory("Length");
  fSensorPosYCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  fSensorPosZCmd = new G4UIcmdWithADoubleAndUnit("/sensor/geom/posZ", this);
  fSensorPosZCmd->SetGuidance(
      "Set sensor center Z position in world coordinates (default is flush on scintillator +Z face when not set)");
  fSensorPosZCmd->SetParameterName("posZ", false);
  fSensorPosZCmd->SetUnitCategory("Length");
  fSensorPosZCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Output format command. Allowed values are constrained by SetCandidates.
  fOutputFormatCmd = new G4UIcmdWithAString("/output/format", this);
  fOutputFormatCmd->SetGuidance("Set output format: csv, hdf5, both");
  fOutputFormatCmd->SetParameterName("format", false);
  fOutputFormatCmd->SetCandidates("csv hdf5 both");
  fOutputFormatCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Output filename command.
  fOutputFilenameCmd = new G4UIcmdWithAString("/output/filename", this);
  fOutputFilenameCmd->SetGuidance(
      "Set output base filename/path; .csv/.h5 extension is added automatically");
  fOutputFilenameCmd->SetParameterName("filename", false);
  fOutputFilenameCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Optional run-name command used for routing outputs to data/<runname>/.
  fOutputRunNameCmd = new G4UIcmdWithAString("/output/runname", this);
  fOutputRunNameCmd->SetGuidance(
      "Set optional run name; outputs go under data/<runname>/. Use \"\" to clear.");
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
  delete fOutputFormatCmd;

  delete fSensorPosZCmd;
  delete fSensorPosYCmd;
  delete fSensorPosXCmd;

  delete fSensorThicknessCmd;
  delete fSensorYCmd;
  delete fSensorXCmd;

  delete fGeomScintPosZCmd;
  delete fGeomScintPosYCmd;
  delete fGeomScintPosXCmd;
  delete fGeomScintZCmd;
  delete fGeomScintYCmd;
  delete fGeomScintXCmd;
  delete fGeomMaterialCmd;

  delete fOutputDir;
  delete fSensorGeomDir;
  delete fSensorDir;
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

  // Sensor dimensions are controlled in dedicated /sensor/geom subtree.
  if (command == fSensorXCmd) {
    fConfig->SetSensorX(fSensorXCmd->GetNewDoubleValue(newValue));
    NotifyGeometryChanged();
    return;
  }

  if (command == fSensorYCmd) {
    fConfig->SetSensorY(fSensorYCmd->GetNewDoubleValue(newValue));
    NotifyGeometryChanged();
    return;
  }

  if (command == fSensorThicknessCmd) {
    fConfig->SetSensorThickness(fSensorThicknessCmd->GetNewDoubleValue(newValue));
    NotifyGeometryChanged();
    return;
  }

  // Sensor absolute center position controls.
  if (command == fSensorPosXCmd) {
    const auto value = fSensorPosXCmd->GetNewDoubleValue(newValue);
    fConfig->SetSensorPosX(value);
    G4cout << "Sensor posX set to " << value / mm << " mm." << G4endl;
    NotifyGeometryChanged();
    return;
  }

  if (command == fSensorPosYCmd) {
    const auto value = fSensorPosYCmd->GetNewDoubleValue(newValue);
    fConfig->SetSensorPosY(value);
    G4cout << "Sensor posY set to " << value / mm << " mm." << G4endl;
    NotifyGeometryChanged();
    return;
  }

  if (command == fSensorPosZCmd) {
    const auto value = fSensorPosZCmd->GetNewDoubleValue(newValue);
    fConfig->SetSensorPosZ(value);
    G4cout << "Sensor posZ set to " << value / mm << " mm." << G4endl;
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

  // Run name controls optional output routing under data/<runname>/.
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
