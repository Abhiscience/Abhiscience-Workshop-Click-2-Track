package com.workshop.click2track.data.db

import androidx.room.*
import androidx.room.TypeConverters
import java.util.*

@Entity(tableName = "pending_captures")
data class PendingCapture(
    @PrimaryKey val event_id: String,
    val stage_id: Int,
    val job_card_id: Int?,
    val vehicle_id: Int?,
    val image_uri: String?,
    val plate_text: String?,
    val confidence: Float?,
    val remarks: String?,
    val created_at: Date,
    val sync_status: String = "PENDING",  // PENDING, SYNCING, SYNCED, FAILED
    val retry_count: Int = 0
)

@Entity(tableName = "user_prefs")
data class UserPreferences(
    @PrimaryKey val user_id: Int,
    val name: String,
    val mobile: String,
    val role_id: Int,
    val branch_id: Int?,
    val installation_id: String?,
    val access_token: String?,
    val last_sync: Date?
)

@Dao
interface PendingCaptureDao {
    @Query("SELECT * FROM pending_captures WHERE sync_status = 'PENDING'")
    suspend fun getPendingCaptures(): List<PendingCapture>

    @Query("SELECT * FROM pending_captures WHERE sync_status = 'FAILED' AND retry_count < 5 ORDER BY created_at ASC")
    suspend fun getFailedCapturesForRetry(): List<PendingCapture>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(capture: PendingCapture)

    @Update
    suspend fun update(capture: PendingCapture)

    @Query("DELETE FROM pending_captures WHERE sync_status = 'SYNCED'")
    suspend fun deleteSynced()
}

@Dao
interface UserPrefsDao {
    @Query("SELECT * FROM user_prefs LIMIT 1")
    suspend fun getUserPreferences(): UserPreferences?
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(prefs: UserPreferences)
}

@Database(
    entities = [PendingCapture::class, UserPreferences::class],
    version = 2
)
@TypeConverters(Converters::class)
abstract class AppDatabase : RoomDatabase() {
    abstract fun pendingCaptureDao(): PendingCaptureDao
    abstract fun userPrefsDao(): UserPrefsDao

    companion object {
        @Volatile
        private var INSTANCE: AppDatabase? = null

        fun getDatabase(context: android.content.Context): AppDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "click2track_database"
                ).fallbackToDestructiveMigration().build()
                INSTANCE = instance
                instance
            }
        }
    }
}

class Converters {
    @TypeConverter
    fun fromDate(date: Date?): Long? = date?.time
    
    @TypeConverter
    fun toDate(millis: Long?): Date? = millis?.let { Date(it) }
}