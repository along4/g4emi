#ifndef structures_h
#define structures_h 1

#include <hdf5.h>

#include <cstddef>
#include <cstdint>
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
 */
struct PrimaryInfo {
  std::int64_t gunCallId = -1;
  std::int32_t primaryTrackId = -1;
  std::string primarySpecies = "unknown";
  double primaryXmm = 0.0;
  double primaryYmm = 0.0;
  double primaryEnergyMeV = 0.0;
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
 */
struct PhotonInfo {
  std::int64_t gunCallId = -1;
  std::int32_t primaryTrackId = -1;
  std::int32_t secondaryTrackId = -1;
  std::int32_t photonTrackId = -1;
  double photonOriginXmm = 0.0;
  double photonOriginYmm = 0.0;
  double photonOriginZmm = 0.0;
  double sensorHitXmm = 0.0;
  double sensorHitYmm = 0.0;
};

/**
 * Flat CSV row container for one detected optical photon hit.
 *
 * This mirrors the CSV schema used by the project so the EventAction module
 * can provide semantic data and the SimIO module can handle formatting/writing.
 */
struct CsvPhotonHitInfo {
  std::int64_t eventId = -1;
  std::int32_t primaryId = -1;
  std::int32_t secondaryId = -1;
  std::int32_t photonId = -1;

  std::string primarySpecies = "unknown";
  double primaryXmm = 0.0;
  double primaryYmm = 0.0;

  std::string secondarySpecies = "unknown";
  double secondaryOriginXmm = 0.0;
  double secondaryOriginYmm = 0.0;
  double secondaryOriginZmm = 0.0;
  double secondaryOriginEnergyMeV = 0.0;

  double scintOriginXmm = 0.0;
  double scintOriginYmm = 0.0;
  double scintOriginZmm = 0.0;

  double sensorHitXmm = 0.0;
  double sensorHitYmm = 0.0;
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
 */
struct Hdf5PhotonNativeRow {
  std::int64_t gun_call_id;
  std::int32_t primary_track_id;
  std::int32_t secondary_track_id;
  std::int32_t photon_track_id;
  double photon_origin_x_mm;
  double photon_origin_y_mm;
  double photon_origin_z_mm;
  double sensor_hit_x_mm;
  double sensor_hit_y_mm;
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
