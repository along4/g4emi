find_package(Geant4 REQUIRED ui_all vis_all)
include(${Geant4_USE_FILE})
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
  ${HDF5_LIBRARIES}
)

# Keep executable path stable as ./build/g4emi.
set_target_properties(g4emi PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY ${PROJECT_BINARY_DIR}
)

# Make macro paths stable when running from the build directory.
file(COPY ${CMAKE_CURRENT_SOURCE_DIR}/macros DESTINATION ${PROJECT_BINARY_DIR}/sim)
