package com.workshop.click2track.data.api

import retrofit2.Response
import retrofit2.http.*
import okhttp3.MultipartBody
import okhttp3.RequestBody

// Data models
// NOTE: backend IDs are integers. Keep these as Int everywhere to avoid
// downstream type mismatches with API paths and JSON payloads.
data class User(
    val user_id: Int,
    val name: String,
    val mobile: String,
    val role_id: Int,
    val branch_id: Int?,
    val status: String
)

data class Role(
    val role_id: Int,
    val role_name: String,
    val capture_label: String?,
    val permissions: Map<String, Boolean>?
)

data class Vehicle(
    val vehicle_id: Int,
    val registration_number: String,
    val make: String?,
    val model: String?,
    val color: String?,
    val region: String?
)

data class JobCard(
    val job_card_id: Int,
    val external_job_card_no: String,
    val vehicle_id: Int?,
    val status: String?,
    val open_time: String?,
    val close_time: String?
)

data class CaptureEvent(
    val event_id: Int,
    val job_card_id: Int?,
    val stage_id: Int,
    val user_id: Int,
    val image_url: String?,
    val plate_text_raw: String?,
    val plate_text_normalized: String?,
    val plate_confidence: Float?,
    val match_status: String?,
    val captured_at_device: String?,
    val remarks: String?
)

// API interfaces
interface ApiService {
    @FormUrlEncoded
    @POST("auth/login")
    suspend fun login(
        @Field("username") mobile: String,
        @Field("password") password: String
    ): Response<LoginResponse>

    @Multipart
    @POST("captures/")
    suspend fun submitCapture(
        @Header("Authorization") authHeader: String,
        @Part("stage_id") stageId: RequestBody,
        @Part("job_card_id") jobCardId: RequestBody?,
        @Part("vehicle_id") vehicleId: RequestBody?,
        @Part("geo_lat") geoLat: RequestBody?,
        @Part("geo_lng") geoLng: RequestBody?,
        @Part("remarks") remarks: RequestBody?,
        @Part image: MultipartBody.Part
    ): Response<CaptureResponse>

    @Multipart
    @POST("captures/override-request")
    suspend fun submitOverrideRequest(
        @Header("Authorization") authHeader: String,
        @Part("stage_id") stageId: RequestBody,
        @Part("reason") reason: RequestBody,
        @Part("job_card_id") jobCardId: RequestBody?,
        @Part("vehicle_id") vehicleId: RequestBody?,
        @Part("plate_text") plateText: RequestBody?,
        @Part("remarks") remarks: RequestBody?,
        @Part("geo_lat") geoLat: RequestBody?,
        @Part("geo_lng") geoLng: RequestBody?,
        @Part image: MultipartBody.Part
    ): Response<OverrideRequestResponse>

    @GET("admin/workflow-stages")
    suspend fun listWorkflowStages(
        @Header("Authorization") authHeader: String,
        @Query("branch_id") branchId: Int
    ): Response<WorkflowStagesResponse>

    @GET("job-cards/active/search")
    suspend fun searchJobCards(@Query("plate") plate: String): Response<JobCardsResponse>

    @GET("job-cards/{job_card_id}/timeline")
    suspend fun getVehicleTimeline(@Path("job_card_id") jobCardId: Int): Response<TimelineResponse>

    @GET("analytics/dashboard/live-workshop-status")
    suspend fun getLiveWorkshopStatus(): Response<LiveStatusResponse>
}

// Real login response shape. The backend returns flat fields, not nested user/role objects.
data class LoginResponse(
    val access_token: String,
    val token_type: String,
    val user_id: Int,
    val role_id: Int
)

data class CaptureResponse(
    val event_id: Int,
    val match_status: String?,
    val image_url: String?
)

data class JobCardsResponse(
    val job_cards: List<JobCard>
)

data class TimelineResponse(
    val vehicle_id: Int,
    val registration_number: String,
    val job_card_id: Int,
    val events: List<TimelineEvent>
)

data class TimelineEvent(
    val event_id: Int,
    val stage_name: String,
    val stage_code: String,
    val user_name: String,
    val role_name: String,
    val captured_at: String,
    val image_url: String?
)

data class LiveStatusResponse(
    val active_vehicles: List<VehicleStatus>,
    val vehicles_by_stage: Map<String, Int>,
    val bottlenecks: List<String>
)

data class VehicleStatus(
    val job_card_id: Int,
    val registration: String,
    val current_stage: String,
    val entered_at: String
)

data class WorkflowStage(
    val stage_id: Int,
    val branch_id: Int?,
    val role_id: Int?,
    val stage_code: String,
    val stage_name: String,
    val sequence_order: Int,
    val capture_mandatory: Boolean?,
    val allow_override: Boolean?,
    val skip_deviation: Boolean?,
    val role_name: String?
)

data class WorkflowStagesResponse(
    val stages: List<WorkflowStage>
)

data class ActiveJobCardsResponse(
    val job_cards: List<ActiveJobCard>
)

data class ActiveJobCard(
    val job_card_id: Int,
    val external_job_card_no: String,
    val vehicle_id: Int?,
    val registration_number: String?,
    val branch_id: Int?,
    val advisor_id: Int?,
    val status: String?,
    val open_time: String?,
    val close_time: String?
)

data class OverrideRequestResponse(
    val override_request_id: Int,
    val status: String,
    val message: String?
)
