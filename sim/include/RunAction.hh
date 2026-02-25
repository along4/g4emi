#ifndef RunAction_h
#define RunAction_h 1

#include "G4UserRunAction.hh"

class G4Run;
class Config;

/// Run-level validation hooks.
class RunAction : public G4UserRunAction {
 public:
  explicit RunAction(const Config* config);
  ~RunAction() override = default;

  /// Validate output paths before event processing starts.
  void BeginOfRunAction(const G4Run* run) override;

 private:
  const Config* fConfig = nullptr;
};

#endif
