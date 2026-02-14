#ifndef PrimaryGeneratorAction_h
#define PrimaryGeneratorAction_h 1

#include "G4VUserPrimaryGeneratorAction.hh"

class G4Event;
class G4GeneralParticleSource;

/// Primary-particle source action backed by Geant4 GPS.
class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction {
 public:
  PrimaryGeneratorAction();
  ~PrimaryGeneratorAction() override;

  /// Generate primary vertex/particles for one Geant4 event.
  void GeneratePrimaries(G4Event* event) override;

 private:
  /// Geant4 GeneralParticleSource configured by macro/UI commands.
  G4GeneralParticleSource* fGPS = nullptr;
};

#endif
