find_package(Geant4 REQUIRED ui_all vis_all)
include(${Geant4_USE_FILE})

# When building inside Pixi/conda, prefer that prefix for HDF5 resolution
# to avoid accidentally mixing Homebrew/system libraries.
if(DEFINED ENV{CONDA_PREFIX})
  list(PREPEND CMAKE_PREFIX_PATH "$ENV{CONDA_PREFIX}")
  set(HDF5_ROOT "$ENV{CONDA_PREFIX}")
endif()

find_package(HDF5 COMPONENTS C HL REQUIRED)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

file(GLOB APP_SOURCES CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/src/*.cc)
file(GLOB APP_HEADERS CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/include/*.hh)

add_executable(g4emi ${CMAKE_CURRENT_SOURCE_DIR}/apps/g4emi_main.cc ${APP_SOURCES} ${APP_HEADERS})

target_include_directories(g4emi PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/include
  ${HDF5_INCLUDE_DIRS}
)

target_link_libraries(g4emi PRIVATE
  ${Geant4_LIBRARIES}
)

if(TARGET HDF5::HDF5)
  target_link_libraries(g4emi PRIVATE HDF5::HDF5)
else()
  target_link_libraries(g4emi PRIVATE ${HDF5_LIBRARIES})
endif()

target_compile_definitions(g4emi PRIVATE
  G4EMI_REPO_ROOT="${CMAKE_SOURCE_DIR}"
)

# Keep executable path stable as ./build/g4emi.
set_target_properties(g4emi PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY ${PROJECT_BINARY_DIR}
)

if(DEFINED ENV{CONDA_PREFIX})
  set_target_properties(g4emi PROPERTIES
    BUILD_RPATH "$ENV{CONDA_PREFIX}/lib"
    INSTALL_RPATH "$ENV{CONDA_PREFIX}/lib"
    INSTALL_RPATH_USE_LINK_PATH FALSE
  )
endif()

# Make macro paths stable when running from the build directory.
file(COPY ${CMAKE_CURRENT_SOURCE_DIR}/macros DESTINATION ${PROJECT_BINARY_DIR}/sim)
