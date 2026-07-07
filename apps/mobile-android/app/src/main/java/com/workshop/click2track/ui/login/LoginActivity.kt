package com.workshop.click2track.ui.login

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.workshop.click2track.BuildConfig
import com.workshop.click2track.data.api.ApiService
import com.workshop.click2track.data.api.LoginResponse
import com.workshop.click2track.data.db.AppDatabase
import com.workshop.click2track.data.db.UserPreferences
import com.workshop.click2track.databinding.ActivityLoginBinding
import com.workshop.click2track.ui.capture.CaptureActivity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

class LoginActivity : AppCompatActivity() {
    private lateinit var binding: ActivityLoginBinding

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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)

        lifecycleScope.launch {
            val prefs = withContext(Dispatchers.IO) { db.userPrefsDao().getUserPreferences() }
            if (prefs?.access_token?.isNotBlank() == true) {
                openStageSelection()
                return@launch
            }
        }

        binding.loginButton.setOnClickListener { attemptLogin() }
    }

    private fun attemptLogin() {
        val mobile = binding.mobileEditText.text.toString().trim()
        val password = binding.passwordEditText.text.toString()

        if (mobile.isBlank() || password.isBlank()) {
            Toast.makeText(this, "Enter mobile number and password", Toast.LENGTH_SHORT).show()
            return
        }

        binding.loginButton.isEnabled = false
        binding.loginButton.text = "Logging in..."

        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val response = apiService.login(mobile, password)
                withContext(Dispatchers.Main) {
                    if (response.isSuccessful) {
                        val body = response.body()
                        if (body != null) {
                            saveSessionAndProceed(body)
                        } else {
                            showError("Empty response from server")
                        }
                    } else {
                        showError("Login failed: ${response.code()}")
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    showError("Network error: ${e.message}")
                }
            } finally {
                withContext(Dispatchers.Main) {
                    binding.loginButton.isEnabled = true
                    binding.loginButton.text = "Login"
                }
            }
        }
    }

    private fun saveSessionAndProceed(body: LoginResponse) {
        lifecycleScope.launch(Dispatchers.IO) {
            // Fetch minimal user info from the token; profile details can be backfilled later.
            val prefs = UserPreferences(
                user_id = body.user_id,
                name = "",
                mobile = binding.mobileEditText.text.toString().trim(),
                role_id = body.role_id,
                branch_id = null,
                installation_id = null,
                access_token = body.access_token,
                last_sync = null
            )
            db.userPrefsDao().insert(prefs)

            withContext(Dispatchers.Main) {
                openStageSelection()
            }
        }
    }

    private fun openStageSelection() {
        startActivity(Intent(this, com.workshop.click2track.ui.stage.StageSelectionActivity::class.java))
        finish()
    }

    private fun showError(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }
}
