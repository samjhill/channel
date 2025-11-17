#!/usr/bin/env python3
"""
Test script to verify the weather bumper system is working correctly.
"""
import os
import sys
from pathlib import Path

# Add the project root to the path
repo_root = Path(__file__).resolve().parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

def test_weather_config():
    """Test that the weather config loads correctly."""
    print("=" * 60)
    print("Testing Weather Configuration")
    print("=" * 60)
    
    from server.services.weather_service import load_weather_config
    
    config = load_weather_config()
    print(f"✓ Config loaded successfully")
    print(f"  Enabled: {config.get('enabled', False)}")
    print(f"  Location: {config.get('location', {}).get('city', 'Unknown')}, {config.get('location', {}).get('region', '')}")
    print(f"  API Key Env Var: {config.get('api_key_env_var', 'Not set')}")
    print()
    
    return config


def test_weather_api_key():
    """Test that the API key is set in the environment."""
    print("=" * 60)
    print("Testing API Key Configuration")
    print("=" * 60)
    
    from server.services.weather_service import load_weather_config
    
    config = load_weather_config()
    api_var = config.get("api_key_env_var", "HBN_WEATHER_API_KEY")
    api_key = os.getenv(api_var)
    
    if api_key:
        # Mask the API key for security
        masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        print(f"✓ API key found in environment variable '{api_var}'")
        print(f"  Key: {masked_key}")
        print()
        return True
    else:
        print(f"✗ API key NOT found in environment variable '{api_var}'")
        print(f"  Please set it with: export {api_var}=your_api_key_here")
        print()
        return False


def test_weather_fetch():
    """Test fetching weather data from the API."""
    print("=" * 60)
    print("Testing Weather API Fetch")
    print("=" * 60)
    
    try:
        import requests
        from server.services.weather_service import get_current_weather, load_weather_config
        
        config = load_weather_config()
        api_var = config.get("api_key_env_var", "HBN_WEATHER_API_KEY")
        api_key = os.getenv(api_var)
        location = config.get("location", {})
        lat = location.get("lat")
        lon = location.get("lon")
        units = config.get("units", "imperial")
        
        # Test the API call directly to see error details
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": lat, "lon": lon, "appid": api_key, "units": units},
            timeout=5,
        )
        
        if resp.status_code == 200:
            weather = get_current_weather()
            if weather:
                print("✓ Successfully fetched weather data!")
                print(f"  Location: {weather.city}, {weather.region}")
                print(f"  Temperature: {weather.temperature:.1f}°F")
                print(f"  Feels like: {weather.feels_like:.1f}°F")
                print(f"  Condition: {weather.condition}")
                print()
                return True
            else:
                print("✗ Weather service returned None despite successful API call")
                print()
                return False
        else:
            try:
                error_data = resp.json()
                error_msg = error_data.get('message', str(error_data))
            except Exception:
                error_msg = resp.text[:200] if resp.text else "Unknown error"
            print(f"✗ API returned status {resp.status_code}")
            print(f"  Error: {error_msg}")
            print()
            return False
            
    except Exception as e:
        print(f"✗ Error testing weather fetch: {e}")
        print("  This could be a network issue or API key problem")
        print()
        return False


def test_weather_renderer():
    """Test that the weather bumper renderer can be imported."""
    print("=" * 60)
    print("Testing Weather Bumper Renderer")
    print("=" * 60)
    
    try:
        from scripts.bumpers.render_weather_bumper import render_weather_bumper
        print("✓ Weather bumper renderer imported successfully")
        print()
        return True
    except ImportError as e:
        print(f"✗ Failed to import weather bumper renderer: {e}")
        print()
        return False


def main():
    """Run all tests."""
    print("\n🧪 Weather Bumper System Test Suite\n")
    
    results = []
    
    # Test 1: Config loading
    try:
        config = test_weather_config()
        results.append(("Config Loading", True))
    except Exception as e:
        print(f"✗ Config loading failed: {e}\n")
        results.append(("Config Loading", False))
        return
    
    # Test 2: API key
    has_api_key = test_weather_api_key()
    results.append(("API Key", has_api_key))
    
    if not has_api_key:
        print("\n⚠️  Cannot test API fetch without API key.")
        print("   Set the API key with:")
        print(f"   export {config.get('api_key_env_var', 'HBN_WEATHER_API_KEY')}=your_api_key_here")
        print()
        return
    
    # Test 3: Weather fetch
    try:
        fetch_success = test_weather_fetch()
        results.append(("Weather API Fetch", fetch_success))
    except Exception as e:
        print(f"✗ Weather fetch test failed: {e}\n")
        results.append(("Weather API Fetch", False))
    
    # Test 4: Renderer import
    try:
        renderer_success = test_weather_renderer()
        results.append(("Renderer Import", renderer_success))
    except Exception as e:
        print(f"✗ Renderer import test failed: {e}\n")
        results.append(("Renderer Import", False))
    
    # Summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")
    
    all_passed = all(result[1] for result in results)
    print()
    if all_passed:
        print("🎉 All tests passed! Weather bumper system is ready.")
    else:
        print("⚠️  Some tests failed. Please fix the issues above.")
    print()


if __name__ == "__main__":
    main()

