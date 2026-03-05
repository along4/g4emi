#ifndef EventAction_h
#define EventAction_h 1

#include "G4ThreeVector.hh"
#include "G4Types.hh"
#include "G4UserEventAction.hh"

#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

class G4Event;
class G4Track;
class Config;

/// Per-event aggregation and HDF5 row assembly.
class EventAction : public G4UserEventAction {
 public:
  /// Track metadata cached by track ID.
  struct TrackInfo {
    std::string species = "unknown";
    G4ThreeVector originPosition;
    G4double originEnergy = -1.0;
    G4int primaryTrackID = -1;
  };

  /// Optical-photon ancestry and creation context.
  struct PhotonCreationInfo {
    G4int primaryTrackID = -1;
    G4int secondaryTrackID = -1;
    G4ThreeVector scintOriginPosition;
    std::string secondarySpecies = "unknown";
    G4ThreeVector secondaryOriginPosition;
    G4double secondaryOriginEnergy = -1.0;
  };

  /// Per-primary activity counters accumulated during stepping/hit capture.
  struct PrimaryActivity {
    std::int64_t createdSecondaryCount = 0;
    std::int64_t generatedOpticalPhotonCount = 0;
    std::int64_t detectedOpticalInterfacePhotonCount = 0;
  };

  /// One detected optical-interface photon hit.
  struct PhotonHitRecord {
    G4int primaryID = -1;
    G4int secondaryID = -1;
    G4int photonID = -1;

    std::string primarySpecies = "unknown";
    G4double primaryX = -1.0;
    G4double primaryY = -1.0;

    std::string secondarySpecies = "unknown";
    G4ThreeVector secondaryOriginPosition;
    G4double secondaryOriginEnergy = -1.0;

    G4ThreeVector scintOriginPosition;
    G4ThreeVector photonScintExitPosition;
    G4bool hasPhotonScintExitPosition = false;

    G4ThreeVector opticalInterfaceHitPosition;
    G4double opticalInterfaceHitTime = -1.0;
    G4ThreeVector opticalInterfaceHitDirection;
    G4ThreeVector opticalInterfaceHitPolarization;
    G4double photonCreationTime = -1.0;
    G4double opticalInterfaceHitEnergy = -1.0;
    G4double opticalInterfaceHitWavelength = -1.0;
  };

  explicit EventAction(const Config* config);
  ~EventAction() override;

  static EventAction* Instance();

  void BeginOfEventAction(const G4Event* event) override;
  void EndOfEventAction(const G4Event* event) override;

  void RecordTrackInfo(G4int trackID, const TrackInfo& info);
  const TrackInfo* FindTrackInfo(G4int trackID) const;

  void RecordPhotonCreationInfo(G4int photonTrackID, const PhotonCreationInfo& info);
  const PhotonCreationInfo* FindPhotonCreationInfo(G4int photonTrackID) const;
  void RecordPendingPhotonOrigin(const G4Track* photonTrack,
                                 const G4ThreeVector& origin);
  bool ConsumePendingPhotonOrigin(const G4Track* photonTrack,
                                  G4ThreeVector* origin);
  void RecordPhotonScintillatorExit(G4int photonTrackID,
                                    const G4ThreeVector& position);
  bool ConsumePhotonScintillatorExit(G4int photonTrackID,
                                     G4ThreeVector* position);

  void RecordPhotonHit(const PhotonHitRecord& hit);
  const std::string& GetPrimarySpecies() const { return fPrimarySpecies; }
  const G4ThreeVector& GetPrimaryPosition() const { return fPrimaryPosition; }

  /// Called from stepping when first non-transportation primary step is seen.
  void RecordPrimaryScintillatorFirstInteraction(G4int primaryTrackID,
                                                 G4double globalTime);

  /// Called from stepping for each created secondary in scintillator.
  void RecordPrimarySecondaryCreation(G4int primaryTrackID,
                                      G4bool generatedOpticalPhoton);

 private:
  static G4ThreadLocal EventAction* fgInstance;

  const Config* fConfig = nullptr;
  std::string fPrimarySpecies = "unknown";
  G4ThreeVector fPrimaryPosition;
  G4double fPrimaryEnergy = -1.0;
  G4double fPrimaryT0Time = 0.0;
  std::unordered_map<G4int, TrackInfo> fTrackInfo;
  std::unordered_map<G4int, PhotonCreationInfo> fPhotonCreationInfo;
  std::unordered_map<const void*, G4ThreeVector> fPendingPhotonOrigin;
  std::unordered_map<G4int, G4ThreeVector> fPhotonScintillatorExit;
  std::unordered_map<G4int, G4double> fPrimaryScintillatorFirstInteractionTime;
  std::unordered_map<G4int, PrimaryActivity> fPrimaryActivity;
  std::vector<PhotonHitRecord> fPhotonHits;
};

#endif
