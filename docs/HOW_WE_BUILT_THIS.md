# How We Built This System (Simple English)

This document explains, in simple words, how we created the Workshop Click-2-Track system.

## Step 1: Understanding the Problem

We learned that car workshops have a problem:
- They already use computer systems for job cards, parts, and billing
- But they cannot see WHERE the actual car is in the workshop RIGHT NOW
- They don't know which worker touched the car and when
- They don't know if work is taking too long

## Step 2: What We Built

We created a system with 3 parts that work together:

### Part A: The Phone App (Android)
- Security guards take a photo when cars enter
- Mechanics take a photo before they start work
- Parts staff take a photo when giving parts
- QC staff take a photo when checking the car
- Everyone must take a fresh photo - no skipping!
- The app reads the car's number plate automatically
- It links the photo to the correct job card

### Part B: The Backend Server
- Stores all the photos and events
- Matches number plates to job cards
- Compares what really happened vs what the old system says
- Calculates: how long cars wait, who is slow, bottlenecks
- Works even when internet is bad (stores data locally)

### Part C: The Dashboard (Web Admin Panel)
- Shows all cars and where they are RIGHT NOW
- Shows which stages take too long
- Shows which workers are busy or idle
- Shows differences between old system and new reality

## Step 3: Key Features Explained

### Number Plate Recognition (UAE + India)
- We built a flexible system that can use different recognition engines
- UAE plates look like: A12345, B67890
- India plates look like: MH01AB1234, DL02CD5678
- The system can switch between engines easily

### Mandatory Photo Capture
- Every worker MUST take a photo before touching a car
- This creates proof of what happened
- No photo = no record of work done

### Deviation Detection (Smart Comparison)
The system compares:
- What the old computer system says happened
- What our photos show actually happened

It finds problems like:
- Work done but not recorded in old system
- Old system says work done, but no photo proof
- Too much waiting time at any stage
- Work done in wrong order

### Works on MacBook (No Android Phone Needed)
- We made special code so you can test on your MacBook
- When no camera is available, app uses image picker
- You select test car photos instead of taking new photos
- Everything else works the same way

## Step 4: How to Run This System

### For Development (on MacBook):
1. Start the backend server (Docker or Python)
2. Open Android Studio on MacBook
3. Run app on emulator
4. Use test images from the `scripts/seed/test-images` folder
5. View dashboard in web browser

### For Production (in Workshop):
1. Install app on Android phones
2. Point app to your live server
3. Configure your old DMS system in settings
4. Train workers to take photos at each stage

## Step 5: Folder Structure Explained

```
workshop-click-2-track/
├── apps/mobile-android/      # Phone app code
├── apps/admin-web/          # Dashboard code  
├── services/api/            # Backend server code
├── scripts/seed/           # Test data and sample images
├── docs/                   # Documentation
└── infra/                  # Server setup files
```

## Step 6: What Each File Does

### Key Backend Files:
- `app/main.py` - Starts the server
- `app/models/` - Defines database tables (users, cars, job cards, events)
- `app/api/` - Contains all API endpoints
- `packages/workflow-engine/` - Logic for finding problems/deviations

### Key Mobile Files:
- `CaptureActivity.kt` - Camera screen that takes photos
- `ApiService.kt` - Talks to backend server
- `AppDatabase.kt` - Stores events when offline

### Key Dashboard Files:
- `app/live-tracking/page.tsx` - Shows live car movement
- `app/analytics/page.tsx` - Shows charts and statistics

## Step 7: Testing Without a Car Workshop

We created test data:
- Sample job cards
- Test car photos with known number plates
- Mock DMS system (pretends to be your old system)

You can test everything using this sample data.

## Step 8: Going Live Checklist

Before using in a real workshop:

1. Change the secret key (important for security)
2. Connect to your real DMS system
3. Add your real workshop workers as users
4. Configure workflow stages for your workshop
5. Train workers on the photo process
6. Test with a few cars first

## Questions?

The technical documentation is in `docs/` folder.
For setup help, see `docs/setup/README.md`.
For MacBook testing, see `docs/setup/emulator.md`.