cmake_minimum_required(VERSION 3.16...3.27)
project(G4EMI LANGUAGES CXX)

find_package(Geant4 REQUIRED ui_all vis_all)
include(${Geant4_USE_FILE})
find_package(HDF5 COMPONENTS C HL REQUIRED)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include_directories(${PROJECT_SOURCE_DIR}/include)

file(GLOB APP_SOURCES CONFIGURE_DEPENDS src/*.cc)
file(GLOB APP_HEADERS CONFIGURE_DEPENDS include/*.hh)

add_executable(g4emi main.cc ${APP_SOURCES} ${APP_HEADERS})
target_link_libraries(g4emi ${Geant4_LIBRARIES})
target_include_directories(g4emi PRIVATE ${HDF5_INCLUDE_DIRS})
target_link_libraries(g4emi ${HDF5_LIBRARIES})

# Make macro paths stable when running from the build directory.
file(COPY macros DESTINATION ${PROJECT_BINARY_DIR})
