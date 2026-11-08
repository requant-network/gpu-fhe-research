# Add only research executables; the pinned library sources remain untouched.
add_executable(requant_ckks_study "${CMAKE_CURRENT_LIST_DIR}/ckks_study.cpp")
target_compile_features(requant_ckks_study PRIVATE cxx_std_20)
target_link_libraries(requant_ckks_study PRIVATE heongpu CUDA::cudart OpenMP::OpenMP_CXX)
set_target_properties(requant_ckks_study PROPERTIES CUDA_SEPARABLE_COMPILATION ON CUDA_RUNTIME_LIBRARY Shared)
add_executable(requant_bootstrap_study "${CMAKE_CURRENT_LIST_DIR}/bootstrap_study.cpp")
target_compile_features(requant_bootstrap_study PRIVATE cxx_std_20)
target_link_libraries(requant_bootstrap_study PRIVATE heongpu CUDA::cudart OpenMP::OpenMP_CXX)
set_target_properties(requant_bootstrap_study PROPERTIES CUDA_SEPARABLE_COMPILATION ON CUDA_RUNTIME_LIBRARY Shared)
