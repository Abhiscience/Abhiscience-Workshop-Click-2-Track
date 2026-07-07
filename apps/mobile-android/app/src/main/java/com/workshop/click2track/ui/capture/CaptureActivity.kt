package com.workshop.click2track.ui.capture

import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Looper
import android.provider.MediaStore
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.workshop.click2track.BuildConfig
import com.workshop.click2track.R
import com.workshop.click2track.data.api.ApiService
import com.workshop.click2track.data.api.CaptureResponse
import com.workshop.click2track.data.db.AppDatabase
import com.workshop.click2track.data.db.PendingCapture
import com.workshop.click2track.databinding.ActivityCaptureBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.io.File
import java.util.*
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class CaptureActivity : AppCompatActivity() {
    private lateinit var binding: ActivityCaptureBinding
    private lateinit var cameraExecutor: ExecutorService
    private var isEmulatorMode = false
    private var pendingCaptureId: String? = null
    private var imageCaptureRef: ImageCapture? = null

    private var currentStageId: Int = -1
    private var currentStageName: String = ""
    private var currentStageCode: String = ""
    private var currentAllowOverride: Boolean = false
    private var currentJobCardId: Int? = null
    private var currentVehicleId: Int? = null
    private var currentManualPlate: String? = null
    private var currentGeoLat: Double? = null
    private var currentGeoLng: Double? = null

    private val apiService: ApiService by lazy {
        Retrofit.Builder()
            .baseUrl(BuildConfig.BASE_URL)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }

    private val db: AppDatabase by lazy {
        AppDatabase.getDatabase(this)
    }

    private val pickImageLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        result.data?.data?.let { uri ->
            processSelectedImage(uri)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityCaptureBinding.inflate(layoutInflater)
        setContentView(binding.root)

        readIntentExtras()
        if (currentStageId <= 0) {
            Toast.makeText(this, "No stage selected", Toast.LENGTH_SHORT).show()
            finish()
            return
        }
        binding.stageNameText?.text = "$currentStageName ($currentStageCode)"

        // Location is captured at moment of photo, not eagerly.

        isEmulatorMode = BuildConfig.EMULATOR_TEST_MODE || !hasCamera()

        if (isEmulatorMode) {
            binding.selectImageButton.setOnClickListener { openGallery() }
            binding.selectImageButton.isEnabled = true
            binding.cameraPreview.visibility = android.view.View.GONE
            Toast.makeText(this, "Emulator Mode: Select from gallery", Toast.LENGTH_SHORT).show()
        } else {
            if (hasCameraPermission()) {
                startCamera()
            } else {
                requestCameraPermission()
            }
        }

        cameraExecutor = Executors.newSingleThreadExecutor()
    }

    private fun readIntentExtras() {
        currentStageId = intent.getIntExtra(EXTRA_STAGE_ID, -1)
        currentStageName = intent.getStringExtra(EXTRA_STAGE_NAME) ?: ""
        currentStageCode = intent.getStringExtra(EXTRA_STAGE_CODE) ?: ""
        currentAllowOverride = intent.getBooleanExtra(EXTRA_ALLOW_OVERRIDE, false)
        val jobCardExtra = intent.getIntExtra(EXTRA_JOB_CARD_ID, -1)
        currentJobCardId = if (jobCardExtra > 0) jobCardExtra else null
        val vehicleExtra = intent.getIntExtra(EXTRA_VEHICLE_ID, -1)
        currentVehicleId = if (vehicleExtra > 0) vehicleExtra else null
        currentManualPlate = intent.getStringExtra(EXTRA_MANUAL_PLATE)?.takeIf { it.isNotBlank() }
    }

    private fun captureLocation(onLocationReady: () -> Unit) {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
            != PackageManager.PERMISSION_GRANTED) {
            onLocationReady()
            return
        }

        try {
            val fusedLocationClient = com.google.android.gms.location.LocationServices.getFusedLocationProviderClient(this)
            val locationRequest = com.google.android.gms.location.LocationRequest.Builder(
                com.google.android.gms.location.Priority.PRIORITY_BALANCED_POWER_ACCURACY, 5000L
            ).build()
            val callback = object : com.google.android.gms.location.LocationCallback() {
                override fun onLocationResult(result: com.google.android.gms.location.LocationResult) {
                    result.lastLocation?.let {
                        currentGeoLat = it.latitude
                        currentGeoLng = it.longitude
                    }
                    fusedLocationClient.removeLocationUpdates(this)
                    onLocationReady()
                }
            }
            fusedLocationClient.requestLocationUpdates(locationRequest, callback, Looper.getMainLooper())
        } catch (e: Exception) {
            onLocationReady()
        }
    }

    private fun hasCamera(): Boolean {
        return packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY)
    }

    private fun hasCameraPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            this, android.Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED
    }

    private fun requestCameraPermission() {
        ActivityCompat.requestPermissions(
            this, arrayOf(android.Manifest.permission.CAMERA), 100
        )
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 100 && grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            Toast.makeText(this, "Camera permission required", Toast.LENGTH_SHORT).show()
        }
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)

        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(binding.cameraPreview.surfaceProvider)
            }

            val imageCapture = ImageCapture.Builder().build().also {
                imageCaptureRef = it
            }

            val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(this, cameraSelector, preview, imageCapture)

                binding.captureButton.setOnClickListener {
                    takePhoto(imageCapture)
                }
            } catch (exc: Exception) {
                Toast.makeText(this, "Camera binding failed", Toast.LENGTH_SHORT).show()
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun takePhoto(imageCapture: ImageCapture) {
        val photoFile = File(externalMediaDirs.firstOrNull() ?: cacheDir, "C2T_${System.currentTimeMillis()}.jpg")
        val outputOptions = ImageCapture.OutputFileOptions.Builder(photoFile).build()

        imageCapture.takePicture(
            outputOptions,
            ContextCompat.getMainExecutor(this),
            object : ImageCapture.OnImageSavedCallback {
                override fun onError(exc: ImageCaptureException) {
                    Toast.makeText(baseContext, "Photo capture failed: ${exc.message}", Toast.LENGTH_SHORT).show()
                }

                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    val savedUri = output.savedUri ?: Uri.fromFile(photoFile)
                    captureLocation { processSelectedImage(savedUri) }
                }
            }
        )
    }

    private fun openGallery() {
        val intent = Intent(Intent.ACTION_PICK, MediaStore.Images.Media.EXTERNAL_CONTENT_URI)
        pickImageLauncher.launch(intent)
    }

    private fun processSelectedImage(uri: Uri) {
        val captureId = UUID.randomUUID().toString()
        pendingCaptureId = captureId

        val pending = PendingCapture(
            event_id = captureId,
            stage_id = currentStageId,
            job_card_id = currentJobCardId,
            vehicle_id = currentVehicleId,
            image_uri = uri.toString(),
            plate_text = currentManualPlate,
            confidence = null,
            remarks = null,
            geo_lat = currentGeoLat,
            geo_lng = currentGeoLng,
            created_at = Date()
        )

        lifecycleScope.launch {
            db.pendingCaptureDao().insert(pending)
            Toast.makeText(this@CaptureActivity, "Photo queued for upload", Toast.LENGTH_SHORT).show()
            uploadCapture(pending)
        }
    }

    private fun uploadCapture(capture: PendingCapture) {
        lifecycleScope.launch(Dispatchers.IO) {
            val token = db.userPrefsDao().getUserPreferences()?.access_token
            if (token.isNullOrBlank()) {
                markFailed(capture, "No auth token")
                return@launch
            }

            val imageUri = capture.image_uri?.let { Uri.parse(it) } ?: run {
                markFailed(capture, "Missing image URI")
                return@launch
            }

            val imageFile = uriToFile(imageUri) ?: run {
                markFailed(capture, "Could not read image")
                return@launch
            }

            try {
                val syncing = capture.copy(sync_status = "SYNCING")
                db.pendingCaptureDao().update(syncing)

                val requestFile = imageFile.asRequestBody("image/jpeg".toMediaTypeOrNull())
                val body = MultipartBody.Part.createFormData("image", imageFile.name, requestFile)

                val response = apiService.submitCapture(
                    authHeader = "Bearer $token",
                    stageId = capture.stage_id,
                    remarks = capture.remarks,
                    workDoneCategoryId = null,
                    partsWait = null,
                    partsWaitRemark = null,
                    geoLat = capture.geo_lat,
                    geoLng = capture.geo_lng,
                    plateText = capture.plate_text,
                    image = body
                )

                withContext(Dispatchers.Main) {
                    if (response.isSuccessful && response.body() != null) {
                        val synced = capture.copy(sync_status = "SYNCED", retry_count = 0)
                        db.pendingCaptureDao().update(synced)
                        db.pendingCaptureDao().deleteSynced()
                        Toast.makeText(this@CaptureActivity, "Upload successful", Toast.LENGTH_SHORT).show()
                    } else {
                        val errorBody = response.errorBody()?.string()
                        if (isRoleLockedError(errorBody)) {
                            if (currentAllowOverride) {
                                showOverridePrompt(capture)
                            } else {
                                markFailed(capture, "Stage locked - override not allowed")
                                Toast.makeText(this@CaptureActivity, "Stage locked", Toast.LENGTH_SHORT).show()
                            }
                        } else {
                            markFailed(capture, "Upload failed: ${response.code()} - $errorBody")
                            Toast.makeText(this@CaptureActivity, "Upload failed: ${response.code()}", Toast.LENGTH_SHORT).show()
                        }
                    }
                }
            } catch (e: Exception) {
                markFailed(capture, e.message ?: "Upload error")
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@CaptureActivity, "Upload error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private suspend fun markFailed(capture: PendingCapture, reason: String) {
        val failed = capture.copy(
            sync_status = "FAILED",
            retry_count = capture.retry_count + 1,
            remarks = if (capture.remarks.isNullOrBlank()) reason else "${capture.remarks} | $reason"
        )
        db.pendingCaptureDao().update(failed)
    }

    private fun uriToFile(uri: Uri): File? {
        return try {
            val inputStream = contentResolver.openInputStream(uri) ?: return null
            val tempFile = File(cacheDir, "upload_${System.currentTimeMillis()}.jpg")
            tempFile.outputStream().use { output ->
                inputStream.copyTo(output)
            }
            tempFile
        } catch (e: Exception) {
            null
        }
    }

    private fun isRoleLockedError(errorBody: String?): Boolean {
        return errorBody?.contains("role-locked", ignoreCase = true) == true ||
                errorBody?.contains("role locked", ignoreCase = true) == true ||
                errorBody?.contains("override request", ignoreCase = true) == true
    }

    private fun showOverridePrompt(capture: PendingCapture) {
        lifecycleScope.launch(Dispatchers.Main) {
            val input = android.widget.EditText(this@CaptureActivity)
            input.hint = "Reason for override"
            AlertDialog.Builder(this@CaptureActivity)
                .setTitle("Stage locked")
                .setMessage("This stage is role-locked. Enter a reason for the override request.")
                .setView(input)
                .setPositiveButton("Submit request") { _, _ ->
                    val reason = input.text.toString().trim()
                    if (reason.isNotBlank()) {
                        submitOverrideRequest(capture, reason)
                    } else {
                        lifecycleScope.launch {
                            markFailed(capture, "Override request cancelled - no reason")
                        }
                        Toast.makeText(this@CaptureActivity, "Override reason required", Toast.LENGTH_SHORT).show()
                    }
                }
                .setNegativeButton("Cancel") { _, _ ->
                    lifecycleScope.launch {
                        markFailed(capture, "Override request cancelled by user")
                    }
                }
                .setCancelable(false)
                .show()
        }
    }

    private fun submitOverrideRequest(capture: PendingCapture, reason: String) {
        lifecycleScope.launch(Dispatchers.IO) {
            val token = db.userPrefsDao().getUserPreferences()?.access_token
            if (token.isNullOrBlank()) {
                markFailed(capture, "No auth token for override request")
                return@launch
            }
            val imageUri = capture.image_uri?.let { Uri.parse(it) } ?: run {
                markFailed(capture, "Missing image URI")
                return@launch
            }
            val imageFile = uriToFile(imageUri) ?: run {
                markFailed(capture, "Could not read image")
                return@launch
            }

            try {
                val syncing = capture.copy(sync_status = "SYNCING")
                db.pendingCaptureDao().update(syncing)

                val requestFile = imageFile.asRequestBody("image/jpeg".toMediaTypeOrNull())
                val body = MultipartBody.Part.createFormData("image", imageFile.name, requestFile)

                val response = apiService.submitOverrideRequest(
                    authHeader = "Bearer $token",
                    stageId = capture.stage_id,
                    reason = reason,
                    jobCardId = capture.job_card_id,
                    vehicleId = capture.vehicle_id,
                    plateText = capture.plate_text,
                    remarks = capture.remarks,
                    workDoneCategoryId = null,
                    geoLat = capture.geo_lat,
                    geoLng = capture.geo_lng,
                    image = body
                )

                withContext(Dispatchers.Main) {
                    if (response.isSuccessful && response.body() != null) {
                        val overrideId = response.body()!!.override_request_id
                        val marked = capture.copy(
                            sync_status = "FAILED",
                            retry_count = capture.retry_count,
                            remarks = "Override request #$overrideId submitted - pending admin approval"
                        )
                        db.pendingCaptureDao().update(marked)
                        Toast.makeText(this@CaptureActivity, "Override request submitted: #$overrideId", Toast.LENGTH_LONG).show()
                    } else {
                        markFailed(capture, "Override submission failed: ${response.code()}")
                        Toast.makeText(this@CaptureActivity, "Override submission failed", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                markFailed(capture, "Override submission error: ${e.message}")
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@CaptureActivity, "Override submission error", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    companion object {
        const val EXTRA_STAGE_ID = "stage_id"
        const val EXTRA_STAGE_NAME = "stage_name"
        const val EXTRA_STAGE_CODE = "stage_code"
        const val EXTRA_ALLOW_OVERRIDE = "allow_override"
        const val EXTRA_JOB_CARD_ID = "job_card_id"
        const val EXTRA_VEHICLE_ID = "vehicle_id"
        const val EXTRA_MANUAL_PLATE = "manual_plate"
    }

    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
    }
}
