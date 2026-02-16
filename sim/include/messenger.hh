#ifndef messenger_h
#define messenger_h 1

#include "G4UImessenger.hh"

class Config;
class G4UIdirectory;
class G4UIcmdWithADoubleAndUnit;
class G4UIcmdWithAString;
class G4UIcommand;

/// Geant4 UI messenger that maps `/scintillator/geom/*`, `/sensor/geom/*`, and `/output/*` commands into `Config` updates.
class Messenger : public G4UImessenger {
 public:
  /// `config` is a shared mutable settings object updated by UI commands.
  explicit Messenger(Config* config);
  ~Messenger() override;

  /// Geant4 command-dispatch entry point.
  void SetNewValue(G4UIcommand* command, G4String newValue) override;

 private:
  /// Notify run manager that geometry must be reinitialized before beamOn.
  void NotifyGeometryChanged() const;

  /// Shared runtime configuration sink.
  Config* fConfig = nullptr;

  /// Command directories for scintillator, sensor, and output controls.
  G4UIdirectory* fScintillatorDir = nullptr;
  G4UIdirectory* fScintillatorGeomDir = nullptr;
  G4UIdirectory* fSensorDir = nullptr;
  G4UIdirectory* fSensorGeomDir = nullptr;
  G4UIdirectory* fOutputDir = nullptr;

  /// Scintillator geometry/material commands.
  G4UIcmdWithAString* fGeomMaterialCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fGeomScintXCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fGeomScintYCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fGeomScintZCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fGeomScintPosXCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fGeomScintPosYCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fGeomScintPosZCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fGeomApertureRadiusCmd = nullptr;

  /// Sensor geometry commands (size + thickness).
  G4UIcmdWithADoubleAndUnit* fSensorXCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fSensorYCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fSensorThicknessCmd = nullptr;

  /// Sensor center-position commands in world coordinates.
  G4UIcmdWithADoubleAndUnit* fSensorPosXCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fSensorPosYCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fSensorPosZCmd = nullptr;

  /// Output configuration commands.
  G4UIcmdWithAString* fOutputFormatCmd = nullptr;
  G4UIcmdWithAString* fOutputFilenameCmd = nullptr;
  G4UIcmdWithAString* fOutputRunNameCmd = nullptr;
};

#endif
