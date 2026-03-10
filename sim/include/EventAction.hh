#ifndef EventAction_h
#define EventAction_h 1

#include "structures.hh"

#include "G4ThreeVector.hh"
#include "G4Types.hh"
#include "G4UserEventAction.hh"

#include <string>
#include <unordered_map>
#include <vector>

class G4Event;
class G4Track;
class Config;

/// Per-event aggregation and HDF5 row assembly.
class EventAction : public G4UserEventAction {
 public:
  using TrackInfo = SimStructures::TrackInfo;
  using PhotonCreationInfo = SimStructures::PhotonCreationInfo;
  using PrimaryActivity = SimStructures::PrimaryActivity;
  using PhotonHitRecord = SimStructures::PhotonHitRecord;

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
  void RecordSecondaryScintillatorEndpoint(G4int secondaryTrackID,
                                           const G4ThreeVector& position);
  bool FindSecondaryScintillatorEndpoint(G4int secondaryTrackID,
                                         G4ThreeVector* position) const;

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
  std::unordered_map<G4int, TrackInfo> fTrackInfo;
  std::unordered_map<G4int, PhotonCreationInfo> fPhotonCreationInfo;
  std::unordered_map<const void*, G4ThreeVector> fPendingPhotonOrigin;
  std::unordered_map<G4int, G4ThreeVector> fPhotonScintillatorExit;
  std::unordered_map<G4int, G4ThreeVector> fSecondaryScintillatorEndpoint;
  std::unordered_map<G4int, G4double> fPrimaryScintillatorFirstInteractionTime;
  std::unordered_map<G4int, PrimaryActivity> fPrimaryActivity;
  std::vector<PhotonHitRecord> fPhotonHits;
};

#endif
