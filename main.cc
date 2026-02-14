#include "ActionInitialization.hh"
#include "DetectorConstruction.hh"
#include "config.hh"
#include "messenger.hh"

#include "FTFP_BERT_HP.hh"
#include "G4OpticalPhysics.hh"
#include "G4OpticalParameters.hh"
#include "G4RunManagerFactory.hh"
#include "G4UIExecutive.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"
#include "G4Types.hh"

#include <memory>

int main(int argc, char** argv) {
  auto* runManager = G4RunManagerFactory::CreateRunManager(G4RunManagerType::Default);

  auto config = std::make_unique<Config>();
  auto* detector = new DetectorConstruction(config.get());
  runManager->SetUserInitialization(detector);
  Messenger messenger(config.get());

  auto* physicsList = new FTFP_BERT_HP();
  physicsList->RegisterPhysics(new G4OpticalPhysics());
  runManager->SetUserInitialization(physicsList);
  G4OpticalParameters::Instance()->SetScintTrackSecondariesFirst(true);

  runManager->SetUserInitialization(new ActionInitialization(detector, config.get()));

  auto* visManager = new G4VisExecutive();
  visManager->Initialize();

  auto* uiManager = G4UImanager::GetUIpointer();
  if (argc > 1) {
    G4String command = "/control/execute ";
    uiManager->ApplyCommand(command + argv[1]);
  } else {
    auto* ui = new G4UIExecutive(argc, argv);
    uiManager->ApplyCommand("/control/execute macros/vis.mac");
    ui->SessionStart();
    delete ui;
  }

  delete visManager;
  delete runManager;
  return 0;
}
