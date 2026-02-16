#ifndef EventAction_h
#define EventAction_h 1

#include "G4ThreeVector.hh"
#include "G4Types.hh"
#include "G4UserEventAction.hh"

#include <string>
#include <unordered_map>
#include <vector>

class G4Event;
class G4Track;
class Config;

/// Per-event aggregation and output-dispatch action.
class EventAction : public G4UserEventAction {
 public:
  /// Per-track origin and ancestry metadata cached within an event.
  struct TrackInfo {
    std::string species = "unknown";
    G4ThreeVector originPosition;
    G4double originEnergy = -1.0;
    G4int primaryTrackID = -1;
  };

  /// Photon creation metadata resolved from tracking/stepping callbacks.
  struct PhotonCreationInfo {
    G4int primaryTrackID = -1;
    G4int secondaryTrackID = -1;
    G4ThreeVector scintOriginPosition;
    std::string secondarySpecies = "unknown";
    G4ThreeVector secondaryOriginPosition;
    G4double secondaryOriginEnergy = -1.0;
  };

  /// Finalized sensor-hit record (one entry per detected optical photon).
  struct PhotonHitRecord {
    /// Geant4 track IDs (event-local).
    G4int primaryID = -1;
    G4int secondaryID = -1;
    G4int photonID = -1;

    /// Event primary metadata carried into each hit row for convenience.
    std::string primarySpecies = "unknown";
    G4double primaryX = -1.0;
    G4double primaryY = -1.0;

    /// Parent-secondary metadata resolved during ancestry reconstruction.
    std::string secondarySpecies = "unknown";
    G4ThreeVector secondaryOriginPosition;
    G4double secondaryOriginEnergy = -1.0;

    /// Optical-photon creation point inside the scintillator volume.
    G4ThreeVector scintOriginPosition;

    /// Sensor-crossing position (world frame) at pre-step boundary entry.
    G4ThreeVector sensorHitPosition;
    /// Unit momentum-direction vector (dx,dy,dz) at sensor crossing.
    G4ThreeVector sensorHitDirection;
    /// Polarization vector at sensor crossing (world frame components).
    G4ThreeVector sensorHitPolarization;
    /// Photon total energy at sensor crossing (Geant4 internal energy units).
    G4double sensorHitEnergy = -1.0;
    /// Photon wavelength at sensor crossing (Geant4 length units).
    G4double sensorHitWavelength = -1.0;
  };

  /// Stores pointer to shared run configuration.
  explicit EventAction(const Config* config);
  ~EventAction() override;

  /// Returns thread-local `EventAction` instance for current worker.
  static EventAction* Instance();

  /// Reset per-event state and cache primary input metadata.
  void BeginOfEventAction(const G4Event* event) override;
  /// Finalize rows and delegate writing to SimIO.
  void EndOfEventAction(const G4Event* event) override;

  /// Accumulate scintillator energy deposition for this event.
  void AddEdep(G4double edep) { fEdep += edep; }
  /// Cache per-track metadata by Geant4 track ID.
  void RecordTrackInfo(G4int trackID, const TrackInfo& info);
  /// Retrieve cached track metadata (or nullptr when missing).
  const TrackInfo* FindTrackInfo(G4int trackID) const;

  /// Cache resolved optical-photon creation context.
  void RecordPhotonCreationInfo(G4int photonTrackID, const PhotonCreationInfo& info);
  /// Retrieve photon creation context (or nullptr when missing).
  const PhotonCreationInfo* FindPhotonCreationInfo(G4int photonTrackID) const;
  /// Store stepping-time optical-photon origin before tracking callback runs.
  void RecordPendingPhotonOrigin(const G4Track* photonTrack,
                                 const G4ThreeVector& origin);
  /// Retrieve-and-remove pending origin; returns false when none exists.
  bool ConsumePendingPhotonOrigin(const G4Track* photonTrack,
                                  G4ThreeVector* origin);

  /// Append one finalized sensor hit including crossing ray state metadata.
  void RecordPhotonHit(const PhotonHitRecord& hit);
  /// Event primary species label.
  const std::string& GetPrimarySpecies() const { return fPrimarySpecies; }
  /// Event primary origin position.
  const G4ThreeVector& GetPrimaryPosition() const { return fPrimaryPosition; }
  /// Event primary kinetic energy at source.
  G4double GetPrimaryEnergy() const { return fPrimaryEnergy; }

 private:
  /// Thread-local singleton pointer used by SD/tracking helpers.
  static G4ThreadLocal EventAction* fgInstance;

  /// Total energy deposited in scoring volume for current event.
  G4double fEdep = 0.0;
  /// Shared runtime configuration.
  const Config* fConfig = nullptr;
  /// Primary particle label for current event.
  std::string fPrimarySpecies = "unknown";
  /// Primary source position for current event.
  G4ThreeVector fPrimaryPosition;
  /// Primary source kinetic energy for current event.
  G4double fPrimaryEnergy = -1.0;
  /// Track ID -> track metadata lookup.
  std::unordered_map<G4int, TrackInfo> fTrackInfo;
  /// Photon track ID -> photon creation metadata lookup.
  std::unordered_map<G4int, PhotonCreationInfo> fPhotonCreationInfo;
  /// Track pointer -> pending origin captured at stepping-time.
  std::unordered_map<const void*, G4ThreeVector> fPendingPhotonOrigin;
  /// Collected sensor-hit rows for end-of-event serialization.
  std::vector<PhotonHitRecord> fPhotonHits;
};

#endif
