#ifndef seed_h
#define seed_h 1

/// RNG seed utilities for Geant4 master seeding.
namespace Seed {

/// Generate and apply fresh Geant4 master seeds and print them.
void SetAutoMasterSeeds();

}  // namespace Seed

#endif
