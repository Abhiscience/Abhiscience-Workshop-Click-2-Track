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
import com.workshop.click2track.BuildConfig
import com.workshop.click2track.R
import com.workshop.click2track.databinding.ActivityCaptureBinding
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class CaptureActivity : AppCompatActivity() {
    private lateinit var binding: ActivityCaptureBinding
    private lateinit var cameraExecutor: ExecutorService
    private var isEmulatorMode = false
    
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
            // Use file picker instead of camera
            binding.selectImageButton.setOnClickListener { openGallery() }
            binding.selectImageButton.isEnabled = true
            binding.cameraPreview.visibility = android.view.View.GONE
            Toast.makeText(this, "Emulator Mode: Select from gallery", Toast.LENGTH_SHORT).show()
        } else {
            // Use camera
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
    
    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        
        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()
            
            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(binding.cameraPreview.surfaceProvider)
            }
            
            val imageCapture = ImageCapture.Builder().build()
            
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
        // Implementation for taking photo
        // Will send to backend for plate recognition
        Toast.makeText(this, "Photo captured - processing", Toast.LENGTH_SHORT).show()
    }
    
    private fun openGallery() {
        val intent = Intent(Intent.ACTION_PICK, MediaStore.Images.Media.EXTERNAL_CONTENT_URI)
        pickImageLauncher.launch(intent)
    }
    
    private fun processSelectedImage(uri: Uri) {
        // Process selected image - extract plate via backend API
        Toast.makeText(this, "Image selected - processing", Toast.LENGTH_SHORT).show()
    }
    
    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
    }
}