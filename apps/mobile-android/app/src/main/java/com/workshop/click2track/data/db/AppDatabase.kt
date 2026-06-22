package com.workshop.click2track.data.db

import androidx.room.*
import androidx.room.TypeConverters
import java.util.*

@Entity(tableName = "pending_captures")
data class PendingCapture(
    @PrimaryKey val event_id: String,
    val stage_id: String,
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
    @PrimaryKey val user_id: String,
    val name: String,
    val mobile: String,
    val role_id: String,
    val branch_id: String,
    val installation_id: String,
    val last_sync: Date?
)

@Dao
interface PendingCaptureDao {
    @Query("SELECT * FROM pending_captures WHERE sync_status = 'PENDING'")
    suspend fun getPendingCaptures(): List<PendingCapture>
    
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
    version = 1
)
@TypeConverters(Converters::class)
abstract class AppDatabase : RoomDatabase() {
    abstract fun pendingCaptureDao(): PendingCaptureDao
    abstract fun userPrefsDao(): UserPrefsDao
}

class Converters {
    @TypeConverter
    fun fromDate(date: Date?): Long? = date?.time
    
    @TypeConverter
    fun toDate(millis: Long?): Date? = millis?.let { Date(it) }
}