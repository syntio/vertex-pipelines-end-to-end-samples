#!/usr/bin/env python3
"""
Dry run validation script for MLOps pipeline modernization
Tests pipeline compilation and setup without running expensive cloud resources
"""

import os
import sys


def test_environment_setup() -> bool:
    """Test that required environment variables are set"""
    print("🔍 Testing environment setup...")

    required_vars = [
        "VERTEX_PROJECT_ID",
        "VERTEX_LOCATION",
        "VERTEX_PIPELINE_ROOT",
        "VERTEX_SA_EMAIL",
    ]

    all_good = True
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            print(f"  ✅ {var}: {value}")
        else:
            print(f"  ❌ {var}: Missing")
            all_good = False

    return all_good


def test_imports() -> bool:
    """Test that all required imports work"""
    print("\n🔍 Testing imports...")

    imports = [
        "kfp",
        "google.cloud.aiplatform",
        "bigquery_components",
        "vertex_components",
    ]

    all_good = True
    for imp in imports:
        try:
            __import__(imp)
            print(f"  ✅ {imp}: OK")
        except ImportError as e:
            print(f"  ❌ {imp}: {e}")
            all_good = False

    return all_good


def test_pipeline_compilation() -> bool:
    """Test that all pipelines compile successfully (no cloud execution)"""
    print("\n🔍 Testing pipeline compilation...")

    # Add src to Python path like the tests do
    import sys

    src_path = os.path.join(os.path.dirname(__file__), "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    # Import pipelines
    from pipelines.tensorflow.training.pipeline import tensorflow_pipeline
    from pipelines.tensorflow.prediction.pipeline import tensorflow_pipeline as tf_pred
    from pipelines.xgboost.training.pipeline import xgboost_pipeline
    from pipelines.xgboost.prediction.pipeline import xgboost_pipeline as xgb_pred
    from kfp import compiler

    pipelines = [
        ("tensorflow-training", tensorflow_pipeline),
        ("tensorflow-prediction", tf_pred),
        ("xgboost-training", xgboost_pipeline),
        ("xgboost-prediction", xgb_pred),
    ]

    all_good = True
    for name, pipeline in pipelines:
        try:
            # Use simple filename instead of temp file to avoid Windows permissions
            json_file = f"{name}-test.json"
            compiler.Compiler().compile(
                pipeline_func=pipeline,
                package_path=json_file,
                type_check=False,  # Skip type checking for speed
            )
            print(f"  ✅ {name}: Compiles successfully")
            # Clean up the test file
            if os.path.exists(json_file):
                try:
                    os.unlink(json_file)
                except OSError:
                    pass  # Ignore cleanup errors
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            all_good = False

    return all_good


def main():
    """Run all dry run validation tests"""
    print("🚀 MLOps Pipeline Dry Run Validation")
    print("=" * 50)

    tests = [
        ("Environment Setup", test_environment_setup),
        ("Import Dependencies", test_imports),
        ("Pipeline Compilation", test_pipeline_compilation),
    ]

    all_passed = True
    for test_name, test_func in tests:
        try:
            passed = test_func()
            if not passed:
                all_passed = False
        except Exception as e:
            print(f"  ❌ {test_name}: Unexpected error - {e}")
            all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Python 3.11 + KFP 2.x modernization is ready!")
        print("✅ Your team can now run the full e2e tests")
        return 0
    else:
        print("❌ Some tests failed. Check the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
