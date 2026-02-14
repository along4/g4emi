#ifndef PhotonSensorSD_h
#define PhotonSensorSD_h 1

#include "G4VSensitiveDetector.hh"

class G4Step;
class G4TouchableHistory;

/// Sensitive detector attached to the back-face photon sensor volume.
class PhotonSensorSD : public G4VSensitiveDetector {
 public:
  explicit PhotonSensorSD(const G4String& name);
  ~PhotonSensorSD() override = default;

  /// Records optical-photon hits and forwards data into EventAction.
  G4bool ProcessHits(G4Step* step, G4TouchableHistory* history) override;
};

#endif
