package com.workshop.click2track.ui.capture

import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.MediaStore
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
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
import okhttp3.RequestBody.Companion.toRequestBody
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

    // TODO: Phase 2 — wire these from the stage-selection UI rather than hardcoding.
    private var currentStageId: Int = 1
    private var currentJobCardId: Int? = null
    private var currentVehicleId: Int? = null

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

        // Check if emulator mode (for MacBook testing)
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
                    processSelectedImage(savedUri)
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
            plate_text = null,
            confidence = null,
            remarks = null,
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
                val stageBody = capture.stage_id.toString().toRequestBody("text/plain".toMediaTypeOrNull())
                val jobCardBody = capture.job_card_id?.toString()?.toRequestBody("text/plain".toMediaTypeOrNull())
                val vehicleBody = capture.vehicle_id?.toString()?.toRequestBody("text/plain".toMediaTypeOrNull())
                val remarksBody = capture.remarks?.toRequestBody("text/plain".toMediaTypeOrNull())

                val response = apiService.submitCapture(
                    authHeader = "Bearer $token",
                    stageId = stageBody,
                    jobCardId = jobCardBody,
                    vehicleId = vehicleBody,
                    remarks = remarksBody,
                    image = body
                )

                withContext(Dispatchers.Main) {
                    if (response.isSuccessful && response.body() != null) {
                        val synced = capture.copy(sync_status = "SYNCED", retry_count = 0)
                        db.pendingCaptureDao().update(synced)
                        db.pendingCaptureDao().deleteSynced()
                        Toast.makeText(this@CaptureActivity, "Upload successful", Toast.LENGTH_SHORT).show()
                    } else {
                        val error = "Upload failed: ${response.code()}"
                        markFailed(capture, error)
                        Toast.makeText(this@CaptureActivity, error, Toast.LENGTH_SHORT).show()
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

    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
    }
}
