#ifndef structures_h
#define structures_h 1

#include "G4ThreeVector.hh"
#include "G4Types.hh"

#include <hdf5.h>

#include <cstddef>
#include <cstdint>
#include <limits>
#include <string>

namespace SimStructures {

/**
 * Primary-particle information container.
 *
 * This struct is populated by simulation logic (e.g. EventAction) and then
 * handed to the IO layer for serialization.
 *
 * Field semantics:
 * - `gunCallId`: Geant4 event ID (`G4Event::GetEventID()`).
 * - `primaryTrackId`: event-local Geant4 track ID of the primary.
 * - `primarySpecies`: compact species label (`n`, `p`, `g`, etc.).
 * - `primaryXmm`, `primaryYmm`: primary origin position in mm.
 * - `primaryEnergyMeV`: primary origin kinetic energy in MeV.
 * - `primaryInteractionTimeNs`: first primary scintillator interaction time
 *   in ns. Written as `NaN` when no scintillator interaction time was
 *   recorded.
 * - `primaryCreatedSecondaryCount`: number of secondaries created in the
 *   scintillator and attributed to this primary ancestry.
 * - `primaryGeneratedOpticalPhotonCount`: number of created optical photons
 *   attributed to this primary ancestry.
 * - `primaryDetectedOpticalInterfacePhotonCount`: number of detected
 *   optical-interface photon hits attributed to this primary ancestry.
 */
struct PrimaryInfo {
  std::int64_t gunCallId = -1;
  std::int32_t primaryTrackId = -1;
  std::string primarySpecies = "unknown";
  double primaryXmm = 0.0;
  double primaryYmm = 0.0;
  double primaryEnergyMeV = 0.0;
  double primaryInteractionTimeNs = std::numeric_limits<double>::quiet_NaN();
  std::int64_t primaryCreatedSecondaryCount = 0;
  std::int64_t primaryGeneratedOpticalPhotonCount = 0;
  std::int64_t primaryDetectedOpticalInterfacePhotonCount = 0;
};

/**
 * Secondary-particle information container.
 *
 * Represents the parent secondary associated with one or more detected
 * optical photons.
 */
struct SecondaryInfo {
  std::int64_t gunCallId = -1;
  std::int32_t primaryTrackId = -1;
  std::int32_t secondaryTrackId = -1;
  std::string secondarySpecies = "unknown";
  double secondaryOriginXmm = 0.0;
  double secondaryOriginYmm = 0.0;
  double secondaryOriginZmm = 0.0;
  double secondaryOriginEnergyMeV = 0.0;
};

/**
 * Optical-photon information container.
 *
 * Represents one detected optical photon row destined for the `/photons`
 * dataset in HDF5 output. This includes both creation-point metadata and
 * optical-interface crossing state needed for downstream optical propagation.
 */
struct PhotonInfo {
  /// Geant4 event ID (`G4Event::GetEventID()`).
  std::int64_t gunCallId = -1;
  /// Geant4 primary-track ID linked to this photon (event-local).
  std::int32_t primaryTrackId = -1;
  /// Geant4 parent-secondary track ID linked to this photon (event-local).
  std::int32_t secondaryTrackId = -1;
  /// Geant4 optical-photon track ID (event-local).
  std::int32_t photonTrackId = -1;
  /// Optical-photon creation time in ns (Geant4 global time basis).
  double photonCreationTimeNs = 0.0;

  /// Photon creation-point position in the scintillator frame, expressed in mm.
  double photonOriginXmm = 0.0;
  double photonOriginYmm = 0.0;
  double photonOriginZmm = 0.0;

  /// Position (mm) where the photon last exited the scintillator volume.
  /// If no scintillator-exit crossing was recorded for this photon, the writer
  /// sets all three `photonScintExit*` components to NaN to indicate "no exit".
  double photonScintExitXmm = 0.0;
  double photonScintExitYmm = 0.0;
  double photonScintExitZmm = 0.0;

  /// Optical-interface entry-point coordinates in mm at the pre-step boundary crossing.
  double opticalInterfaceHitXmm = 0.0;
  double opticalInterfaceHitYmm = 0.0;
  /// Optical-interface crossing time in ns (Geant4 global time basis).
  double opticalInterfaceHitTimeNs = 0.0;

  /// Unit momentum-direction components at optical-interface crossing.
  double opticalInterfaceHitDirX = 0.0;
  double opticalInterfaceHitDirY = 0.0;
  double opticalInterfaceHitDirZ = 0.0;

  /// Polarization-vector components at optical-interface crossing.
  double opticalInterfaceHitPolX = 0.0;
  double opticalInterfaceHitPolY = 0.0;
  double opticalInterfaceHitPolZ = 0.0;

  /// Total photon energy at optical-interface crossing in eV.
  double opticalInterfaceHitEnergyEV = -1.0;
  /// Photon wavelength at optical-interface crossing in nm.
  double opticalInterfaceHitWavelengthNm = -1.0;
};

/// Event-local track metadata cached by Geant4 track ID.
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

namespace detail {

/**
 * Fixed-size string width for species labels in HDF5 compound datasets.
 *
 * Chosen as a compact but sufficient size for particle symbols and isotope
 * labels while keeping row footprint small.
 */
constexpr std::size_t kHdf5SpeciesLabelSize = 24;

/**
 * Binary/native row layout for `/primaries` HDF5 dataset.
 *
 * This layout is intentionally POD-like and uses fixed-size arrays to match
 * HDF5 compound-type requirements.
 */
struct Hdf5PrimaryNativeRow {
  std::int64_t gun_call_id;
  std::int32_t primary_track_id;
  char primary_species[kHdf5SpeciesLabelSize];
  double primary_x_mm;
  double primary_y_mm;
  double primary_energy_MeV;
  double primary_interaction_time_ns;
  std::int64_t primary_created_secondary_count;
  std::int64_t primary_generated_optical_photon_count;
  std::int64_t primary_detected_optical_interface_photon_count;
};

/**
 * Binary/native row layout for `/secondaries` HDF5 dataset.
 */
struct Hdf5SecondaryNativeRow {
  std::int64_t gun_call_id;
  std::int32_t primary_track_id;
  std::int32_t secondary_track_id;
  char secondary_species[kHdf5SpeciesLabelSize];
  double secondary_origin_x_mm;
  double secondary_origin_y_mm;
  double secondary_origin_z_mm;
  double secondary_origin_energy_MeV;
};

/**
 * Binary/native row layout for `/photons` HDF5 dataset.
 *
 * Field names/ordering mirror the semantic PhotonInfo container above. Keep
 * this struct POD-compatible for HDF5 compound writes.
 */
struct Hdf5PhotonNativeRow {
  std::int64_t gun_call_id;
  std::int32_t primary_track_id;
  std::int32_t secondary_track_id;
  std::int32_t photon_track_id;
  double photon_creation_time_ns;
  double photon_origin_x_mm;
  double photon_origin_y_mm;
  double photon_origin_z_mm;
  double photon_scint_exit_x_mm;
  double photon_scint_exit_y_mm;
  double photon_scint_exit_z_mm;
  double optical_interface_hit_x_mm;
  double optical_interface_hit_y_mm;
  double optical_interface_hit_time_ns;
  double optical_interface_hit_dir_x;
  double optical_interface_hit_dir_y;
  double optical_interface_hit_dir_z;
  double optical_interface_hit_pol_x;
  double optical_interface_hit_pol_y;
  double optical_interface_hit_pol_z;
  double optical_interface_hit_energy_eV;
  double optical_interface_hit_wavelength_nm;
};

/**
 * Process-global handle state for open HDF5 resources.
 *
 * This is internal writer state and not analysis data.
 */
struct Hdf5State {
  hid_t file = -1;
  hid_t primaryType = -1;
  hid_t secondaryType = -1;
  hid_t photonType = -1;
  hid_t primariesDs = -1;
  hid_t secondariesDs = -1;
  hid_t photonsDs = -1;
  std::string openPath;
  bool registeredAtExit = false;
};

}  // namespace detail

}  // namespace SimStructures

#endif
