#include "messenger.hh"

#include "config.hh"

#include "G4ApplicationState.hh"
#include "G4RunManager.hh"
#include "G4UIcmdWithADoubleAndUnit.hh"
#include "G4UIcmdWithAString.hh"
#include "G4UIdirectory.hh"
#include "G4ios.hh"

/**
 * Geant4 UI messenger responsible for runtime configuration commands.
 *
 * Responsibilities:
 * - Register `/scintillator/geom/...` and `/output/...` command hierarchy.
 * - Parse user-provided command values.
 * - Forward validated values into the shared Config object.
 * - Notify the run manager when geometry-affecting fields are modified.
 */
Messenger::Messenger(Config* config) : fConfig(config) {
  // Top-level namespace for this application's custom commands.
  fScintillatorDir = new G4UIdirectory("/scintillator/");
  fScintillatorDir->SetGuidance("Application controls");

  // Geometry subtree (material and dimensions).
  fGeomDir = new G4UIdirectory("/scintillator/geom/");
  fGeomDir->SetGuidance("Geometry controls");

  // Output subtree (format and file destinations).
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

  // Sensor thickness command; still treated as geometry-changing.
  fGeomSensorThicknessCmd =
      new G4UIcmdWithADoubleAndUnit("/scintillator/geom/sensorThickness", this);
  fGeomSensorThicknessCmd->SetGuidance("Set back-face sensor thickness");
  fGeomSensorThicknessCmd->SetParameterName("sensorThickness", false);
  fGeomSensorThicknessCmd->SetUnitCategory("Length");
  fGeomSensorThicknessCmd->SetRange("sensorThickness > 0.");
  fGeomSensorThicknessCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Output format command. Allowed values are constrained by SetCandidates.
  fOutputFormatCmd = new G4UIcmdWithAString("/output/format", this);
  fOutputFormatCmd->SetGuidance("Set output format: csv, hdf5, both");
  fOutputFormatCmd->SetParameterName("format", false);
  fOutputFormatCmd->SetCandidates("csv hdf5 both");
  fOutputFormatCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // CSV file path command.
  fOutputCsvFileCmd = new G4UIcmdWithAString("/output/csvFile", this);
  fOutputCsvFileCmd->SetGuidance("Set CSV output file path");
  fOutputCsvFileCmd->SetParameterName("csvFile", false);
  fOutputCsvFileCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // HDF5 file path command.
  fOutputHdf5FileCmd = new G4UIcmdWithAString("/output/hdf5File", this);
  fOutputHdf5FileCmd->SetGuidance("Set HDF5 output file path");
  fOutputHdf5FileCmd->SetParameterName("hdf5File", false);
  fOutputHdf5FileCmd->AvailableForStates(G4State_PreInit, G4State_Idle);
}

/**
 * Destroy all UI command and directory objects owned by this messenger.
 *
 * Deletion is performed in reverse ownership order for clarity and to mirror
 * constructor allocation flow.
 */
Messenger::~Messenger() {
  delete fOutputHdf5FileCmd;
  delete fOutputCsvFileCmd;
  delete fOutputFormatCmd;

  delete fGeomSensorThicknessCmd;
  delete fGeomScintZCmd;
  delete fGeomScintYCmd;
  delete fGeomScintXCmd;
  delete fGeomMaterialCmd;

  delete fOutputDir;
  delete fGeomDir;
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

  // Dimension updates are parsed in configured units by Geant4 command helpers.
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

  if (command == fGeomSensorThicknessCmd) {
    fConfig->SetSensorThickness(
        fGeomSensorThicknessCmd->GetNewDoubleValue(newValue));
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

  // Output path updates only change destination, not simulation state.
  if (command == fOutputCsvFileCmd) {
    fConfig->SetCsvFile(newValue);
    G4cout << "CSV output file set to '" << fConfig->GetCsvFile() << "'." << G4endl;
    return;
  }

  if (command == fOutputHdf5FileCmd) {
    fConfig->SetHdf5File(newValue);
    G4cout << "HDF5 output file set to '" << fConfig->GetHdf5File() << "'."
           << G4endl;
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
    runManager->GeometryHasBeenModified();
  }
  G4cout << "Geometry updated. Run /run/initialize before /beamOn." << G4endl;
}
