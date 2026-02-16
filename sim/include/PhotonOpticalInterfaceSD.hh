#ifndef PhotonOpticalInterfaceSD_h
#define PhotonOpticalInterfaceSD_h 1

#include "G4VSensitiveDetector.hh"

class G4Step;
class G4TouchableHistory;

/// Sensitive detector attached to the back-face optical-interface volume.
class PhotonOpticalInterfaceSD : public G4VSensitiveDetector {
 public:
  explicit PhotonOpticalInterfaceSD(const G4String& name);
  ~PhotonOpticalInterfaceSD() override = default;

  /// Records optical-photon hits and forwards data into EventAction.
  G4bool ProcessHits(G4Step* step, G4TouchableHistory* history) override;
};

#endif
