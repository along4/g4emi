#include "PhotonSensorSD.hh"

#include "EventAction.hh"

#include "G4OpticalPhoton.hh"
#include "G4ParticleDefinition.hh"
#include "G4PhysicalConstants.hh"
#include "G4Step.hh"
#include "G4StepPoint.hh"
#include "G4SystemOfUnits.hh"
#include "G4Track.hh"
#include "G4TrackStatus.hh"

/**
 * Construct the optical-photon sensor sensitive detector.
 *
 * The detector name is registered with Geant4's SD manager and is used to bind
 * this SD instance to the back-face sensor logical volume in
 * DetectorConstruction::ConstructSDandField().
 */
PhotonSensorSD::PhotonSensorSD(const G4String& name) : G4VSensitiveDetector(name) {}

/**
 * Process a hit inside the sensor volume.
 *
 * Behavior and intent:
 * - Accept only optical-photon tracks; all other particles are ignored.
 * - Build one EventAction::PhotonHitRecord per accepted photon crossing.
 * - Capture sensor-entry ray state from the pre-step point:
 *   position, momentum direction, polarization, and total energy.
 * - Derive wavelength from energy (`lambda = h*c/E`) and store both.
 * - Prefer rich ancestry metadata precomputed in TrackingAction
 *   (FindPhotonCreationInfo).
 * - Fall back to minimal track-derived fields when ancestry metadata is missing.
 * - Stop and kill the photon after recording the hit so each detected photon
 *   contributes at most one sensor record.
 *
 * Return value:
 * - true  -> this step was handled as a valid optical-photon sensor hit.
 * - false -> ignored (null step, non-optical track, or missing EventAction).
 */
G4bool PhotonSensorSD::ProcessHits(G4Step* step, G4TouchableHistory*) {
  // Defensive check: Geant4 should provide a valid step, but guard anyway.
  if (!step) {
    return false;
  }

  auto* track = step->GetTrack();
  // This SD is defined only for optical photons; reject everything else.
  if (!track ||
      track->GetParticleDefinition() != G4OpticalPhoton::OpticalPhotonDefinition()) {
    return false;
  }

  // EventAction stores all per-event containers (track ancestry + output rows).
  // If it is unavailable, we cannot persist this hit safely.
  auto* eventAction = EventAction::Instance();
  if (!eventAction) {
    return false;
  }

  EventAction::PhotonHitRecord hit;

  // Photon-local identifiers and event-level primary context.
  hit.photonID = track->GetTrackID();
  hit.primarySpecies = eventAction->GetPrimarySpecies();
  hit.primaryX = eventAction->GetPrimaryPosition().x();
  hit.primaryY = eventAction->GetPrimaryPosition().y();

  // Pre-step point corresponds to entry into the sensitive volume.
  // We capture full ray state here for downstream optical propagation.
  const auto* preStep = step->GetPreStepPoint();
  hit.sensorHitPosition = preStep->GetPosition();
  hit.sensorHitDirection = preStep->GetMomentumDirection();
  hit.sensorHitPolarization = preStep->GetPolarization();
  hit.sensorHitEnergy = preStep->GetTotalEnergy();

  // Convert energy to wavelength using Geant4 physical constants.
  // Keep the default sentinel (-1) when energy is non-positive.
  if (hit.sensorHitEnergy > 0.0) {
    hit.sensorHitWavelength = (h_Planck * c_light) / hit.sensorHitEnergy;
  }

  // Preferred path: TrackingAction already resolved primary/secondary ancestry
  // and scintillation origin for this optical photon track.
  if (const auto* creationInfo =
          eventAction->FindPhotonCreationInfo(track->GetTrackID())) {
    hit.primaryID = creationInfo->primaryTrackID;
    hit.secondaryID = creationInfo->secondaryTrackID;
    hit.secondarySpecies = creationInfo->secondarySpecies;
    hit.secondaryOriginPosition = creationInfo->secondaryOriginPosition;
    hit.secondaryOriginEnergy = creationInfo->secondaryOriginEnergy;
    hit.scintOriginPosition = creationInfo->scintOriginPosition;
  } else {
    // Fallback path: keep output row valid even when ancestry bookkeeping is
    // incomplete (for example, if track linkage was not available).
    if (const auto* trackInfo = eventAction->FindTrackInfo(track->GetTrackID())) {
      hit.primaryID = trackInfo->primaryTrackID;
    }

    hit.secondaryID = track->GetParentID();
    hit.secondarySpecies = "unknown";
    hit.secondaryOriginPosition = G4ThreeVector();
    hit.secondaryOriginEnergy = -1.0;

    // Vertex position is the best available estimate of photon creation point.
    hit.scintOriginPosition = track->GetVertexPosition();
  }

  // Commit one finalized hit row for this photon.
  eventAction->RecordPhotonHit(hit);

  // Terminate the photon after hit registration to avoid duplicate detections
  // from further transport steps inside/after the sensor volume.
  track->SetTrackStatus(fStopAndKill);
  return true;
}
