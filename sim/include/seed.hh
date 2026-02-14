#ifndef seed_h
#define seed_h 1

/// RNG seed utilities for process-level Geant4 master seeding.
namespace Seed {

/// Generate and apply fresh Geant4 master seeds, then print them to stdout.
void SetAutoMasterSeeds();

}  // namespace Seed

#endif
