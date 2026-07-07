package com.workshop.click2track.ui.stage

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.*
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.workshop.click2track.BuildConfig
import com.workshop.click2track.R
import com.workshop.click2track.data.api.ActiveJobCard
import com.workshop.click2track.data.api.ApiService
import com.workshop.click2track.data.api.WorkflowStage
import com.workshop.click2track.data.db.AppDatabase
import com.workshop.click2track.data.db.UserPreferences
import com.workshop.click2track.databinding.ActivityStageSelectionBinding
import com.workshop.click2track.ui.capture.CaptureActivity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

class StageSelectionActivity : AppCompatActivity() {
    private lateinit var binding: ActivityStageSelectionBinding
    private var selectedStage: WorkflowStage? = null
    private var selectedJobCard: ActiveJobCard? = null
    private var manuallyEnteredPlate: String? = null

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
        binding = ActivityStageSelectionBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.searchJobCardButton.setOnClickListener { searchJobCards() }
        binding.manualPlateButton.setOnClickListener { showManualPlateDialog() }
        binding.proceedButton.setOnClickListener { proceedToCapture() }
        binding.clearSelectionButton.setOnClickListener { clearJobCardSelection() }

        binding.proceedButton.isEnabled = false

        loadStages()
        ensureLocationPermission()
    }

    private fun loadStages() {
        lifecycleScope.launch(Dispatchers.IO) {
            val prefs = db.userPrefsDao().getUserPreferences()
            val token = prefs?.access_token
            val branchId = prefs?.branch_id
            if (token.isNullOrBlank() || branchId == null) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@StageSelectionActivity, "Session not ready", Toast.LENGTH_SHORT).show()
                }
                return@launch
            }

            try {
                val response = apiService.listWorkflowStages("Bearer $token", branchId)
                withContext(Dispatchers.Main) {
                    if (response.isSuccessful && response.body() != null) {
                        currentStages = response.body()!!.stages
                        renderStages(currentStages, prefs)
                    } else {
                        Toast.makeText(this@StageSelectionActivity, "Could not load stages", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@StageSelectionActivity, "Error loading stages: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun renderStages(stages: List<WorkflowStage>, prefs: UserPreferences) {
        binding.stageListLayout.removeAllViews()

        val userRoleId = prefs.role_id
        val roleLockedStages = stages.filter { it.role_id == userRoleId && it.role_id != null }
        val otherStages = stages.filter { it.role_id != userRoleId || it.role_id == null }

        val listContainer = binding.stageListLayout

        if (roleLockedStages.isNotEmpty()) {
            addSectionHeader(listContainer, "Your stages")
            roleLockedStages.forEach { addStageRow(listContainer, it) }
        }

        if (otherStages.isNotEmpty()) {
            addSectionHeader(listContainer, "Other stages (override required)")
            otherStages.forEach { addStageRow(listContainer, it) }
        }

        if (stages.isEmpty()) {
            addSectionHeader(listContainer, "No stages available")
        }
    }

    private fun addSectionHeader(container: LinearLayout, text: String) {
        TextView(this).apply {
            this.text = text
            textSize = 16f
            setPadding(0, 16, 0, 8)
        }.also { container.addView(it) }
    }

    private fun addStageRow(container: LinearLayout, stage: WorkflowStage) {
        val row = LayoutInflater.from(this).inflate(R.layout.item_stage, container, false)
        val nameView = row.findViewById<TextView>(R.id.stageNameText)
        val codeView = row.findViewById<TextView>(R.id.stageCodeText)
        val radio = row.findViewById<RadioButton>(R.id.stageRadioButton)

        nameView.text = stage.stage_name
        codeView.text = "${stage.stage_code} ${if (stage.capture_mandatory == true) "*" else ""}".trim()
        radio.isChecked = (selectedStage?.stage_id == stage.stage_id)

        row.setOnClickListener {
            selectedStage = stage
            updateSelectionUI()
            // Radio state is refreshed by re-rendering; for a larger list use a RecyclerView adapter.
            renderByBackingList()
        }

        container.addView(row)
    }

    private var currentStages: List<WorkflowStage> = emptyList()
    private fun renderByBackingList() {
        lifecycleScope.launch(Dispatchers.IO) {
            val prefs = db.userPrefsDao().getUserPreferences()
            withContext(Dispatchers.Main) {
                prefs?.let { renderStages(currentStages, it) }
            }
        }
    }

    private fun updateSelectionUI() {
        val stage = selectedStage
        binding.selectedStageText.text = stage?.let {
            "Stage: ${it.stage_name} (${it.stage_code})"
        } ?: "No stage selected"
        binding.proceedButton.isEnabled = (stage != null)
    }

    private fun searchJobCards() {
        val query = binding.plateSearchEditText.text.toString().trim()
        if (query.isBlank()) {
            Toast.makeText(this, "Enter plate number", Toast.LENGTH_SHORT).show()
            return
        }

        lifecycleScope.launch(Dispatchers.IO) {
            val token = db.userPrefsDao().getUserPreferences()?.access_token
            if (token.isNullOrBlank()) return@launch

            try {
                val response = apiService.searchJobCards(query)
                withContext(Dispatchers.Main) {
                    if (response.isSuccessful && response.body() != null) {
                        showJobCardPicker(response.body()!!.job_cards)
                    } else {
                        Toast.makeText(this@StageSelectionActivity, "Search failed", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@StageSelectionActivity, "Search error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun showJobCardPicker(jobCards: List<ActiveJobCard>) {
        if (jobCards.isEmpty()) {
            Toast.makeText(this, "No active job cards found", Toast.LENGTH_SHORT).show()
            return
        }

        val items = jobCards.map { jc ->
            "${jc.registration_number ?: "Unknown"} - ${jc.external_job_card_no}"
        }.toTypedArray()

        AlertDialog.Builder(this)
            .setTitle("Select job card")
            .setItems(items) { _, which ->
                selectedJobCard = jobCards[which]
                manuallyEnteredPlate = null
                updateJobCardSelectionUI()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showManualPlateDialog() {
        val input = EditText(this)
        input.hint = "Enter plate number"
        AlertDialog.Builder(this)
            .setTitle("Manual plate")
            .setView(input)
            .setPositiveButton("OK") { _, _ ->
                val plate = input.text.toString().trim()
                if (plate.isNotBlank()) {
                    selectedJobCard = null
                    manuallyEnteredPlate = plate
                    updateJobCardSelectionUI()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun updateJobCardSelectionUI() {
        val text = when {
            selectedJobCard != null -> "Job card: ${selectedJobCard!!.external_job_card_no} (${selectedJobCard!!.registration_number})"
            !manuallyEnteredPlate.isNullOrBlank() -> "Manual plate: $manuallyEnteredPlate"
            else -> "No job card / plate selected"
        }
        binding.selectedJobCardText.text = text
        binding.clearSelectionButton.visibility =
            if (selectedJobCard != null || !manuallyEnteredPlate.isNullOrBlank()) View.VISIBLE else View.GONE
    }

    private fun clearJobCardSelection() {
        selectedJobCard = null
        manuallyEnteredPlate = null
        updateJobCardSelectionUI()
    }

    private fun proceedToCapture() {
        val stage = selectedStage ?: run {
            Toast.makeText(this, "Select a stage first", Toast.LENGTH_SHORT).show()
            return
        }

        val intent = Intent(this, CaptureActivity::class.java).apply {
            putExtra(CaptureActivity.EXTRA_STAGE_ID, stage.stage_id)
            putExtra(CaptureActivity.EXTRA_STAGE_NAME, stage.stage_name)
            putExtra(CaptureActivity.EXTRA_STAGE_CODE, stage.stage_code)
            putExtra(CaptureActivity.EXTRA_ALLOW_OVERRIDE, stage.allow_override == true)
            putExtra(CaptureActivity.EXTRA_JOB_CARD_ID, selectedJobCard?.job_card_id ?: -1)
            putExtra(CaptureActivity.EXTRA_VEHICLE_ID, selectedJobCard?.vehicle_id ?: -1)
            putExtra(CaptureActivity.EXTRA_MANUAL_PLATE, manuallyEnteredPlate ?: "")
        }
        startActivity(intent)
    }

    private fun ensureLocationPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
            != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION),
                REQUEST_LOCATION_CODE
            )
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        // Permission result is informational. Capture continues even if denied.
    }

    companion object {
        private const val REQUEST_LOCATION_CODE = 101
    }
}
