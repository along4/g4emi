#ifndef messenger_h
#define messenger_h 1

#include "G4UImessenger.hh"

class Config;
class G4UIdirectory;
class G4UIcmdWithADouble;
class G4UIcmdWithADoubleAndUnit;
class G4UIcmdWithAnInteger;
class G4UIcmdWithAString;
class G4UIcommand;

/// Geant4 UI messenger that maps `/scintillator/*`, `/optical_interface/geom/*`, and `/output/*` commands into `Config` updates.
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

  /// Command directories for scintillator, optical-interface, and output controls.
  G4UIdirectory* fScintillatorDir = nullptr;
  G4UIdirectory* fScintillatorGeomDir = nullptr;
  G4UIdirectory* fScintillatorPropertiesDir = nullptr;
  G4UIdirectory* fOpticalInterfaceDir = nullptr;
  G4UIdirectory* fOpticalInterfaceGeomDir = nullptr;
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
  G4UIcmdWithADoubleAndUnit* fScintDensityCmd = nullptr;
  G4UIcmdWithAnInteger* fScintCarbonAtomsCmd = nullptr;
  G4UIcmdWithAnInteger* fScintHydrogenAtomsCmd = nullptr;
  G4UIcmdWithAString* fScintPhotonEnergyCmd = nullptr;
  G4UIcmdWithAString* fScintRIndexCmd = nullptr;
  G4UIcmdWithAString* fScintAbsLengthCmd = nullptr;
  G4UIcmdWithAString* fScintSpectrumCmd = nullptr;
  G4UIcmdWithADouble* fScintYieldCmd = nullptr;
  G4UIcmdWithADouble* fScintResolutionScaleCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fScintTimeConstantCmd = nullptr;
  G4UIcmdWithADouble* fScintYield1Cmd = nullptr;

  /// Optical-interface geometry commands (size + thickness).
  G4UIcmdWithADoubleAndUnit* fOpticalInterfaceXCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fOpticalInterfaceYCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fOpticalInterfaceThicknessCmd = nullptr;

  /// Optical-interface center-position commands in world coordinates.
  G4UIcmdWithADoubleAndUnit* fOpticalInterfacePosXCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fOpticalInterfacePosYCmd = nullptr;
  G4UIcmdWithADoubleAndUnit* fOpticalInterfacePosZCmd = nullptr;

  /// Output configuration commands.
  G4UIcmdWithAString* fOutputFormatCmd = nullptr;
  G4UIcmdWithAString* fOutputPathCmd = nullptr;
  G4UIcmdWithAString* fOutputFilenameCmd = nullptr;
  G4UIcmdWithAString* fOutputRunNameCmd = nullptr;
};

#endif
